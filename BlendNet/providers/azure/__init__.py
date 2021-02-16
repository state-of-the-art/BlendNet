'''Microsoft Azure
Provide API access to allocate required resources in Azure
Dependencies: azure cli installed and configured auth
Help: https://github.com/state-of-the-art/BlendNet/wiki/HOWTO:-Setup-provider:-Azure
'''

__all__ = [
    'Processor',
    'Manager',
    'Agent',
    'Instance',
]

# Exception to notify that the command returned exitcode != 0
class AzToolException(Exception):
    pass

import os
import sys
import json
import platform
import tempfile
import ssl
import site
import urllib
import subprocess
import pathlib

METADATA_URL = 'http://169.254.169.254/metadata/instance/'

LOCATION = None # If the script is running in the cloud
AZ_CONF = {}

AZ_EXEC_OPTIONS = None
AZ_CACHE_LOCATIONS = []
AZ_CACHE_SIZES = None

def _requestMetadata(path, verbose = False):
    req = urllib.request.Request(METADATA_URL+path+'?api-version=2020-10-01&format=text"')
    req.add_header('Metadata','true')
    try:
        while True:
            with urllib.request.urlopen(req, timeout=1) as res:
                if res.getcode() == 503:
                    print('WARN: Azure: Unable to reach metadata serivce')
                    time.sleep(5)
                    continue
                data = res.read()
                try:
                    return data.decode('utf-8')
                except (LookupError, UnicodeDecodeError):
                    # UTF-8 not worked, so probably it's latin1
                    return data.decode('iso-8859-1')
    except Exception as e:
        if verbose:
            print('WARN: Azure: Metadata is not available ' + path)
        return None

def checkLocation():
    '''Returns True if it's the Azure environment'''
    global LOCATION

    if LOCATION is not None:
        return LOCATION

    LOCATION = _requestMetadata('compute/location', True) is not None
    return LOCATION

def _executeAzTool(*args, data=None):
    '''Runs the az tool and returns code and data as tuple, data will be sent to stdin as bytes'''
    cmd = (AZ_CONF.get('az_exec_path'),) + args + AZ_EXEC_OPTIONS
    result = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise AzToolException('Az tool returned %d during execution of "%s": %s' % (
            result.returncode, cmd, result.stderr))

    data = None
    try:
        data = json.loads(result.stdout)
    except UnicodeDecodeError as e:
        print('WARN: Azure: Found UnicodeDecodeError during parsing of the az output, switching to ISO-8859-1:', str(e))
        data = json.loads(result.stdout.decode('iso-8859-1'))
    except json.decoder.JSONDecodeError:
        pass

    return data

def _initAzTool():
    '''Init the az cli with the required parameters'''
    # Login on azure VM with identity
    if checkLocation():
        _executeAzTool('login', '--identity')

    # Get available locations
    global AZ_CACHE_SIZES, AZ_CACHE_LOCATIONS
    AZ_CACHE_SIZES = None
    locations = _executeAzTool('account', 'list-locations')
    AZ_CACHE_LOCATIONS = [('please select', 'please select', 'please select')]
    AZ_CACHE_LOCATIONS += sorted( (l['name'], l['name'], l['regionalDisplayName']) for l in locations )

    return True

def initProvider(settings = dict()):
    '''Finds absolute path to the az tool'''
    from .. import findPATHExec
    global AZ_CONF
    AZ_CONF = settings
    if not AZ_CONF.get('az_exec_path'):
        AZ_CONF['az_exec_path'] = findPATHExec('az')
    if not AZ_CONF.get('location'):
        AZ_CONF['location'] = 'westus'
        if checkLocation():
            AZ_CONF['location'] = _requestMetadata('instance/location')
    if not AZ_CONF.get('resource_group'):
        AZ_CONF['resource_group'] = _requestMetadata('instance/resourceGroupName') if checkLocation() else 'blendnet'
    if not AZ_CONF.get('storage_account'):
        AZ_CONF['storage_account'] = 'blendnet{session_id}'

    if not AZ_CONF['az_exec_path']:
        return 'Unable to find "az" in PATH - check the provider documentation and install the requirements'

    if not os.path.isfile(AZ_CONF['az_exec_path']):
        path = AZ_CONF['az_exec_path']
        AZ_CONF['az_exec_path'] = {}
        return 'The provided "az" exec path is invalid: %s' % (path,)

    global AZ_EXEC_OPTIONS
    AZ_EXEC_OPTIONS = ('--output', 'json')

    if not _initAzTool():
        AZ_CONF['az_exec_path'] = None
        return 'Error during execution of "az" tool'

    print('INFO: Azure: Using az tool:', AZ_CONF['az_exec_path'])

    return True

def checkDependencies(settings):
    if not AZ_CONF.get('az_exec_path'):
        return initProvider(settings)
    return True

def _getLocationItems(scene = None, context = None):
    '''Will return items for enum blender property'''
    return AZ_CACHE_LOCATIONS

def getSettings():
    '''Returns the available settings of the provider'''
    return {
        'az_exec_path': {
            'name': 'Path to az exec',
            'description': 'Full path to the az or az.exe from Azure CLI, by default uses PATH env to find it',
            'type': 'path',
            'value': AZ_CONF.get('az_exec_path'),
        },
        'location': {
            'name': 'Location of resources',
            'description': 'Select the required location for resources provision',
            'type': 'choice',
            'values': _getLocationItems,
            'value': AZ_CONF.get('location'),
        },
        'resource_group': {
            'name': 'Resource group',
            'description': 'Set the resource group name to organize your resources, will be created if not exists',
            'type': 'string',
            'value': AZ_CONF.get('resource_group'),
        },
        'storage_account': {
            'name': 'Storage account',
            'description': '''What kind of storage account to use - in case it's empty will create the new one as "blendnet{session_id}"''',
            'type': 'string',
            'value': AZ_CONF.get('storage_account'),
        },
        'storage_container': {
            'name': 'Storage container',
            'description': '''What the storage container to use - in case it's empty will create the new one as "blendnet-{session_id}"''',
            'type': 'string',
            'value': AZ_CONF.get('storage_container'),
        },
    }

def _getInstanceTypeInfo(name):
    '''Get info about the instance type'''
    try:
        # Update the cache
        getInstanceTypes()
        return { 'cpu': AZ_CACHE_SIZES[name][0], 'mem': AZ_CACHE_SIZES[name][1] }
    except:
        print('ERROR: Azure: Unable to get the Azure machine type info for:', name)

    return None

def _verifyQuotas(avail):
    try:
        import bpy
    except:
        return []

    errors = []

    prefs = bpy.context.preferences.addons[__package__.split('.', 1)[0]].preferences
    manager_info = _getInstanceTypeInfo(prefs.manager_instance_type)
    agents_info = _getInstanceTypeInfo(prefs.manager_agent_instance_type)
    agents_num = prefs.manager_agents_max

    # Manager
    if manager_info:
        if avail.get('Total vCPUs', 0) < manager_info['cpu']:
            errors.append('Available "Total vCPUs" is too small to provision the Manager')
        if avail.get('IP Addresses', 0) < 1: # External addresses
            errors.append('Available "Public IP Addresses" is too small to provision the Manager')
    else:
        errors.append('Unable to get the Manager type info to validate quotas')

    # Agents
    if agents_info:
        if avail.get('Total vCPUs', 0) < agents_info['cpu'] * agents_num:
            errors.append('Available "Total vCPUs" is too small to provision the Agents')
    else:
        errors.append('Unable to get the Agents type info to validate quotas')

    # Common
    if manager_info and agents_info:
        if avail.get('Virtual Machines', 0) < 1 + agents_num:
            errors.append('Available "Virtual Machines" is too small to provision the Manager and Agents')
    else:
        errors.append('Unable to get the Manager and Agents type info to validate quotas')

    if errors:
        errors.append('You can request Azure project quotas increase to get better experience')

    return errors

def getProviderInfo():
    configs = dict()
    try:
        useful_quotas = {
            'cores': 'Total vCPUs',
            'virtualMachines': 'Virtual Machines',
            'PublicIPAddresses': 'IP Addresses',
        }

        avail = {}

        # VM quotas
        data = _executeAzTool('vm', 'list-usage', '--location', AZ_CONF['location'])

        for q in data:
            if q['name']['value'] in useful_quotas:
                avail[useful_quotas[q['name']['value']]] = float(q['limit']) - float(q['currentValue'])
                configs['Quota: ' + useful_quotas[q['name']['value']]] = '%s, usage: %s' % (q['limit'], q['currentValue'])

        # Network quotas
        data = _executeAzTool('network', 'list-usages', '--location', AZ_CONF['location'])

        for q in data:
            if q['name']['value'] in useful_quotas:
                avail[useful_quotas[q['name']['value']]] = float(q['limit']) - float(q['currentValue'])
                configs['Quota: ' + useful_quotas[q['name']['value']]] = '%s, usage: %s' % (q['limit'], q['currentValue'])

        errors = _verifyQuotas(avail)
        if errors:
            configs['ERRORS'] = errors

    except AzToolException as e:
        configs['ERRORS'] = ['Looks like access to the API is restricted '
                             '- please check your permissions: %s' % e]

    return configs

def getInstanceTypes():
    global AZ_CACHE_SIZES
    try:
        if not AZ_CACHE_SIZES:
            data = _executeAzTool('vm', 'list-sizes', '--location', AZ_CONF['location'])
            AZ_CACHE_SIZES = dict([ (d['name'], (d['numberOfCores'], d['memoryInMb'])) for d in data ])
        return dict([ (k, ('%s vCPUs %s GB RAM' % (v[0], v[1]/1024.0), v[1]/1024.0)) for k, v in AZ_CACHE_SIZES.items() ])
    except AzToolException as e:
        return {'ERROR': 'Looks like access to the API is restricted '
                         '- please check your permissions: %s' % e}
    return {}

def _createResourceGroup():
    '''Will check if the resource group existing and create if it's not'''
    data = _executeAzTool('group', 'list', '--query', "[?location=='{}']".format(AZ_CONF['location']))
    groups_list = ( res['name'] for res in data )
    if AZ_CONF['resource_group'] not in groups_list:
        _executeAzTool('group', 'create', '--location', AZ_CONF['location'], '--name', AZ_CONF['resource_group'])

def _createIdentities():
    '''Will ensure the required identities are here'''

    print('INFO: Azure: Creating the identity blendnet-agent')
    agent = _executeAzTool('identity', 'create',
                           '--location', AZ_CONF['location'],
                           '--resource-group', AZ_CONF['resource_group'],
                           '--name', 'blendnet-agent')

    print('INFO: Azure: Creating the identity blendnet-manager')
    mngr = _executeAzTool('identity', 'create',
                          '--location', AZ_CONF['location'],
                          '--resource-group', AZ_CONF['resource_group'],
                          '--name', 'blendnet-manager')

    # Create assignments after idenities, because they take some time appear

    # Use Reader access for Agent to download data from containers
    _executeAzTool('role', 'assignment', 'create',
                   '--role', 'Reader and Data Access',
                   '--assignee-object-id', agent['principalId'],
                   '--description', 'Allow to download from storage for BlendNet Agent',
                   '--resource-group', AZ_CONF['resource_group'])

    # Use Network access for Manager to create VM
    _executeAzTool('role', 'assignment', 'create',
                   '--role', 'Network Contributor',
                   '--assignee-object-id', mngr['principalId'],
                   '--description', 'Allow to create Agent VMs for BlendNet Manager',
                   '--resource-group', AZ_CONF['resource_group'])

    # Create VM access for Manager
    _executeAzTool('role', 'assignment', 'create',
                   '--role', 'Virtual Machine Contributor',
                   '--assignee-object-id', mngr['principalId'],
                   '--description', 'Allow to create Agent VMs for BlendNet Manager',
                   '--resource-group', AZ_CONF['resource_group'])

    # Use blendnet-agent identity access for Manager
    _executeAzTool('role', 'assignment', 'create',
                   '--role', 'Managed Identity Operator',
                   '--assignee-object-id', mngr['principalId'],
                   '--description', 'Allow to create Agent VMs for BlendNet Manager',
                   '--scope', agent['id'])

    print('INFO: Azure: Created identities')

def createInstanceManager(cfg):
    '''Creating a new instance for BlendNet Manager'''
    _createResourceGroup()
    _createIdentities()

    image = 'Debian:debian-10:10:latest'

    account = urllib.parse.urlparse(cfg['storage_url']).hostname.split('.')[0]
    container = urllib.parse.urlparse(cfg['storage_url']).path.split('/')[-1]

    # TODO: make script overridable
    # TODO: too much hardcode here
    startup_script = '''#!/bin/sh
echo '--> Check for blender dependencies'
dpkg -l libxrender1 libxi6 libgl1
if [ $? -gt 0 ]; then
    apt update
    until apt install --no-install-recommends -y libxrender1 libxi6 libgl1; do
        echo "Unable to install blender dependencies, repeating..."
        sleep 5
    done
fi

if [ ! -x /srv/blender/blender ]; then
    echo '--> Download & unpack blender'
    echo "{blender_sha256} -" > /tmp/blender.sha256
    curl -fLs "{blender_url}" | tee /tmp/blender.tar.bz2 | sha256sum -c /tmp/blender.sha256 || (echo "ERROR: checksum of the blender binary is incorrect"; exit 1)
    mkdir -p /srv/blender
    tar -C /srv/blender --strip-components=1 --checkpoint=10000 --checkpoint-action=echo='Unpacked %{{r}}T' -xf /tmp/blender.tar.bz2
fi

# Azure instances has no preinstalled az cli
if ! which az; then
    echo '--> Install az CLI'
    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
fi

cat <<'EOF' > /usr/local/bin/blendnet_cloud_init.sh
#!/bin/sh -e

# Login to identity
az login --identity

echo '--> Update the BlendNet manager'
az storage copy --recursive --source-account-name {storage_account} --source-container {storage_name} --source-blob 'work_manager/*' -d "$(getent passwd blendnet-user | cut -d: -f6)"
# Remove not working due to exception: Exception: MSI auth not yet supported.
# az storage remove --recursive --account-name {storage_account} --container-name {storage_name} --name work_manager
az storage blob delete-batch --account-name {storage_account} --source {storage_name} --pattern 'work_manager/*'
az storage copy --recursive --source-account-name {storage_account} --source-container {storage_name} --source-blob 'blendnet' -d /srv

chown -R blendnet-user .azure .azcopy
EOF

chmod +x /usr/local/bin/blendnet_cloud_init.sh
adduser --shell /bin/false --disabled-password blendnet-user

cat <<'EOF' > /etc/systemd/system/blendnet-manager.service
[Unit]
Description=BlendNet Manager Service
After=network-online.target google-network-daemon.service

[Service]
User=blendnet-user
WorkingDirectory=~
Type=simple
ExecStartPre=+/usr/local/bin/blendnet_cloud_init.sh
ExecStart=/srv/blender/blender -b -noaudio -P /srv/blendnet/manager.py
Restart=always
TimeoutStopSec=60
StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=multi-user.target
EOF

echo '--> Run the BlendNet manager'
systemctl daemon-reload
systemctl enable blendnet-manager.service
systemctl start blendnet-manager.service
'''.format(
        blender_url=cfg['dist_url'],
        blender_sha256=cfg['dist_checksum'],
        session_id=cfg['session_id'],
        storage_account=account,
        storage_name=container,
    )

    options = [
        'vm', 'create',
        '--name', cfg['instance_name'],
        '--resource-group', AZ_CONF['resource_group'],
        '--image', image,
        '--size', cfg['instance_type'],
        '--os-disk-size-gb', '200',
        '--generate-ssh-keys', # For ssh access use '--admin-username', 'blendnet-admin', '--ssh-key-values', '@/home/user/.ssh/id_rsa.pub',
        '--assign-identity', 'blendnet-manager',
        '--nsg', 'blendnet-manager',
        '--custom-data', startup_script,
        # "vm" tag is used to remove the related VM resources
        '--tags', 'app=blendnet', 'session_id='+cfg['session_id'], 'type=manager', 'vm='+cfg['instance_name'],
    ]

    # Creating an instance
    print('INFO: Azure: Creating manager', cfg['instance_name'])
    _executeAzTool(*options)

    return cfg['instance_name']

def createInstanceAgent(cfg):
    '''Creating a new instance for BlendNet Agent'''

    image = 'Debian:debian-10:10:latest'

    account = urllib.parse.urlparse(cfg['storage_url']).hostname.split('.')[0]
    container = urllib.parse.urlparse(cfg['storage_url']).path.split('/')[-1]
    # TODO: make script overridable
    # TODO: too much hardcode here
    startup_script = '''#!/bin/sh
echo '--> Check for blender dependencies'
dpkg -l libxrender1 libxi6 libgl1
if [ $? -gt 0 ]; then
    apt update
    until apt install --no-install-recommends -y libxrender1 libxi6 libgl1; do
        echo "Unable to install blender dependencies, repeating..."
        sleep 5
    done
fi

if [ ! -x /srv/blender/blender ]; then
    echo '--> Download & unpack blender'
    echo "{blender_sha256} -" > /tmp/blender.sha256
    curl -fLs "{blender_url}" | tee /tmp/blender.tar.bz2 | sha256sum -c /tmp/blender.sha256 || (echo "ERROR: checksum of the blender binary is incorrect"; exit 1)
    mkdir -p /srv/blender
    tar -C /srv/blender --strip-components=1 --checkpoint=10000 --checkpoint-action=echo='Unpacked %{{r}}T' -xf /tmp/blender.tar.bz2
fi

# Azure instances has no preinstalled az cli
if ! which az; then
    echo '--> Install az CLI'
    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
fi

cat <<'EOF' > /usr/local/bin/blendnet_cloud_init.sh
#!/bin/sh -e

# Login to identity
az login --identity

echo '--> Update the BlendNet agent'
az storage copy --recursive --source-account-name {storage_account} --source-container {storage_name} --source-blob 'work_{instance_name}/*' -d "$(getent passwd blendnet-user | cut -d: -f6)"
az storage copy --recursive --source-account-name {storage_account} --source-container {storage_name} --source-blob 'blendnet' -d /srv

chown -R blendnet-user .azure .azcopy
EOF

chmod +x /usr/local/bin/blendnet_cloud_init.sh
adduser --shell /bin/false --disabled-password blendnet-user

cat <<'EOF' > /etc/systemd/system/blendnet-agent.service
[Unit]
Description=BlendNet Agent Service
After=network-online.target google-network-daemon.service

[Service]
User=blendnet-user
WorkingDirectory=~
Type=simple
ExecStartPre=+/usr/local/bin/blendnet_cloud_init.sh
ExecStart=/srv/blender/blender -b -noaudio -P /srv/blendnet/agent.py
Restart=always
TimeoutStopSec=20
StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=multi-user.target
EOF

echo '--> Run the BlendNet agent'
systemctl daemon-reload
systemctl enable blendnet-agent.service
systemctl start blendnet-agent.service
    '''.format(
        blender_url=cfg['dist_url'],
        blender_sha256=cfg['dist_checksum'],
        storage_account=account,
        storage_name=container,
        instance_name=cfg['instance_name'],
    )

    options = [
        'vm', 'create',
        '--name', cfg['instance_name'],
        '--resource-group', AZ_CONF['resource_group'],
        '--image', image,
        '--size', cfg['instance_type'],
        '--os-disk-size-gb', '200',
        '--generate-ssh-keys', # For ssh access use '--admin-username', 'blendnet-admin', '--ssh-key-values', '<place_pubkey_here>',
        '--assign-identity', 'blendnet-agent',
        '--nsg', 'blendnet-agent',
        '--public-ip-address', '', # Disable public IP address for the agent (comment it for ssh access)
        '--custom-data', startup_script,
        # "vm" tag is used to remove the related VM resources
        '--tags', 'app=blendnet', 'session_id='+cfg['session_id'], 'type=agent', 'vm='+cfg['instance_name'],
    ]

    if cfg['use_cheap_instance']:
        # Running cheap instance
        print('INFO: Azure: Running cheap agent instance with max price %f (min %f)' % (
            cfg['instance_max_price'],
            getMinimalCheapPrice(cfg['instance_type']),
        ))
        options.append('--priority')
        options.append('Spot')
        options.append('--max-price')
        options.append(str(cfg['instance_max_price']))
        options.append('--eviction-policy')
        options.append('Delete')

    # Creating an instance
    print('INFO: Azure: Creating agent %s' % (cfg['instance_name'],))
    _executeAzTool(*options)

    return cfg['instance_name']

def startInstance(instance_id):
    '''Start stopped instance with specified name'''

    _executeAzTool('vm', 'start',
                   '--resource-group', AZ_CONF['resource_group'],
                   '--name', instance_id)

def stopInstance(instance_id):
    '''Stop instance with specified name'''

    _executeAzTool('vm', 'stop',
                   '--resource-group', AZ_CONF['resource_group'],
                   '--name', instance_id)

def deleteInstance(instance_id):
    '''Delete the instance with specified name'''
    # WARNING: Uses "vm" tag to remove all the related resources

    # Get resources with the res = instance_id
    toremove_ids = _executeAzTool('resource', 'list',
                                  '--tag', 'vm=' + instance_id, '--query', '[].id')
    if len(toremove_ids) < 5:
        print('WARN: Azure: Not enough resources for VM to remove (5 needed): %s' % (toremove_ids,))

    # Remove related resources
    _executeAzTool('resource', 'delete',
                   '--resource-group', AZ_CONF['resource_group'],
                   '--ids', *toremove_ids)

def createFirewall(target_group, port):
    '''Create minimal firewall to access Manager / Agent'''

    # Create the network security group
    print('INFO: Azure: Creating security group for %s' % (target_group,))
    _executeAzTool('network', 'nsg', 'create',
                   '--name', target_group,
                   '--location', AZ_CONF['location'],
                   '--resource-group', AZ_CONF['resource_group'])
    # Disable SSH access
    _executeAzTool('network', 'nsg', 'rule', 'create',
                   '--name', 'inbound-ssh',
                   '--resource-group', AZ_CONF['resource_group'],
                   '--nsg-name', target_group,
                   '--priority', '1000',
                   '--access', 'Deny', # Change 'Deny' to 'Allow' in case you need SSH access
                   '--direction', 'Inbound',
                   '--protocol', 'Tcp',
                   '--destination-port-ranges', '22',
                   '--destination-address-prefixes', '0.0.0.0/0')
    # Allow blendnet ports access
    _executeAzTool('network', 'nsg', 'rule', 'create',
                   '--name', 'inbound-https',
                   '--resource-group', AZ_CONF['resource_group'],
                   '--nsg-name', target_group,
                   '--priority', '1001',
                   '--access', 'Allow',
                   '--direction', 'Inbound',
                   '--protocol', 'Tcp',
                   '--destination-port-ranges', str(port),
                   '--destination-address-prefixes', '10.0.0.0/8' if target_group == 'blendnet-agent' else '0.0.0.0/0')

def createStorage(storage_url):
    '''Creates storage if it's not exists'''

    _createResourceGroup()

    print('INFO: Azure: Creating storage %s ...' % (storage_url,))

    account = urllib.parse.urlparse(storage_url).hostname.split('.')[0]
    container = urllib.parse.urlparse(storage_url).path.split('/')[-1]

    # Using storage account / storage container for azure
    _executeAzTool('storage', 'account', 'create',
                   '--name', account,
                   '--location', AZ_CONF['location'],
                   '--resource-group', AZ_CONF['resource_group'])

    # Wait for account
    while _executeAzTool('storage', 'account', 'check-name',
                         '--name', account).get('nameAvailable'):
        print('DEBUG: Azure: Waiting for account creation')

    _executeAzTool('storage', 'container', 'create',
                   '--name', container,
                   '--account-name', account)

    # Wait for container
    while not _executeAzTool('storage', 'container', 'exists',
                             '--name', container, '--account-name', account).get('exists'):
        print('DEBUG: Azure: Waiting for container creation')

    return True

def uploadFileToStorage(path, storage_url, dest_path = None):
    '''Upload file to the storage'''

    if dest_path:
        if platform.system() == 'Windows':
            dest_path = pathlib.PurePath(dest_path).as_posix()
        storage_url += '/' + dest_path

    # Weird bug in az copy, it don't like relative paths not started with dir
    if not os.path.isabs(path):
        path = os.path.join('.', path)

    print('INFO: Azure: Uploading file to %s ...' % (storage_url,))

    _executeAzTool('storage', 'copy',
                   '--source-local-path', path,
                   '--destination', storage_url)

    return True

def uploadRecursiveToStorage(path, storage_url, dest_path = None, include = None, exclude = None):
    '''Recursively upload files to the storage'''

    if dest_path:
        if platform.system() == 'Windows':
            dest_path = pathlib.PurePath(dest_path).as_posix()
        storage_url += '/' + dest_path

    print('INFO: Azure: Uploading files from %s to "%s" ...' % (path, storage_url))

    cmd = ['storage', 'copy', '--recursive', '--source-local-path', os.path.join(path, '*'), '--destination', storage_url]
    if include:
        cmd += ['--include-pattern', include]
    if exclude:
        cmd += ['--exclude-pattern', exclude]

    _executeAzTool(*cmd)

    print('INFO: Azure: Uploaded files to "%s"' % (storage_url,))

    return True

def uploadDataToStorage(data, storage_url, dest_path = None):
    '''Upload data to the storage'''
    # WARN: tempfile.NamedTemporaryFile is not allowed to be used by a subprocesses on Win

    # No way to use az cli to upload stdin data, so using temp dir & file
    with tempfile.TemporaryDirectory(prefix='blendnet') as temp_dir_name:
        temp_file = os.path.join(temp_dir_name, 'upload_file')
        with open(temp_file, 'wb') as fd:
            fd.write(data)
            fd.flush()

        if dest_path:
            if platform.system() == 'Windows':
                dest_path = pathlib.PurePath(dest_path).as_posix()
            storage_url += '/' + dest_path

        print('INFO: Azure: Uploading data to "%s" ...' % (storage_url,))
        _executeAzTool('storage', 'copy',
                       '--source-local-path', temp_file,
                       '--destination', storage_url)

    return True

def downloadDataFromStorage(storage_url, path = None):
    temp_file = tempfile.NamedTemporaryFile()

    if path:
        if platform.system() == 'Windows':
            path = pathlib.PurePath(path).as_posix()
        storage_url += '/' + path

    print('INFO: Azure: Downloading file from "%s" ...' % (path,))

    try:
        _executeAzTool('storage', 'copy',
                       '--source', storage_url,
                       '--destination-local-path', temp_file.name)
    except AzToolException:
        print('WARN: Azure: Download operation failed')
        return None

    # The original temp_file is unlinked, so reread it
    with open(temp_file.name, 'rb') as fh:
        return fh.read()

def getResources(session_id):
    '''Get the allocated resources with a specific session_id'''
    out = {'agents':{}}

    def parseInstanceInfo(it):
        try:
            return {
                'id': it.get('name'),
                'name': it.get('name'),
                'ip': it.get('publicIps'),
                'internal_ip': it['privateIps'],
                'type': it['hardwareProfile']['vmSize'],
                'started': it['powerState'] == 'VM running',
                'stopped': it['powerState'] == 'VM stopped',
                'created': 'unknown', # TODO: actually available in resources, but not sure it's worth the delay
            }
        except:
            return None

    data = _executeAzTool('vm', 'list', '--show-details',
                          '--resource-group', AZ_CONF['resource_group'],
                          '--query', "[?tags.session_id == '%s']" % (session_id,))

    for it in data:
        inst = parseInstanceInfo(it)
        if not inst:
            continue
        it_type = it['tags'].get('type')
        if it_type == 'manager':
            out['manager'] = inst
        elif it_type == 'agent':
            out['agents'][inst['name']] = inst
        else:
            print('WARN: Azure: Unknown type resource instance', inst['name'])

    return out

def getManagerSizeDefault():
    return 'Standard_A1_v2'

def getAgentSizeDefault():
    # Standard_B and some other are not support Spot VMs
    # https://docs.microsoft.com/en-us/azure/virtual-machines/spot-vms#limitations
    return 'Standard_A1_v2'

def getStorageUrl(session_id):
    '''Returns the azure storage url'''
    default_account = 'blendnet{session_id}'.format(session_id=session_id.lower())
    default_name = 'blendnet-{session_id}'.format(session_id=session_id.lower())
    return 'https://%s.blob.core.windows.net/%s' % (
        (AZ_CONF.get('storage_account') or default_account).format(session_id=session_id.lower()),
        (AZ_CONF.get('storage_container') or default_name).format(session_id=session_id.lower()),
    )

def getManagerName(session_id):
    return 'blendnet-%s-manager' % session_id

def getAgentsNamePrefix(session_id):
    return 'blendnet-%s-agent-' % session_id

def getCheapMultiplierList():
    '''Azure supports spot instances which is market based on spot price'''
    return [0.35] + [ i/100.0 for i in range(1, 100) ]

def getPrice(inst_type, cheap_multiplier):
    '''Returns the price of the instance type per hour for the current region'''
    ctx = ssl.create_default_context()
    for path in site.getsitepackages():
        path = os.path.join(path, 'certifi', 'cacert.pem')
        if not os.path.exists(path):
            continue
        ctx.load_verify_locations(cafile=path)
        break

    if len(ctx.get_ca_certs()) == 0:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    url = 'https://prices.azure.com/api/retail/prices'
    filt = "priceType eq 'Consumption' and serviceName eq 'Virtual Machines' and " \
           "armRegionName eq '%s' and armSkuName eq '%s'" % (AZ_CONF['location'], inst_type)
    params = urllib.parse.urlencode({'$filter': filt})
    url += '?' + params
    req = urllib.request.Request(url)
    try:
        while True:
            with urllib.request.urlopen(req, timeout=5, context=ctx) as res:
                if res.getcode() == 503:
                    print('WARN: Azure: Unable to reach price url')
                    time.sleep(5)
                    continue
                data = json.load(res)
                for d in data['Items']:
                    # Skip windows prices & low priority machines
                    if d['productName'].endswith('Windows') or d['skuName'].endswith('Low Priority'):
                        continue

                    # Return spot price only if multiplier <0 is selected
                    if cheap_multiplier < 0:
                        if not d['skuName'].endswith('Spot'):
                            continue
                        return (d['unitPrice'], d['currencyCode'])
                    elif d['skuName'].endswith('Spot'):
                        continue

                    return (d['unitPrice'] * cheap_multiplier, d['currencyCode'])

                return (-1.0, 'ERR: Unable to find the price')
    except Exception as e:
        print('WARN: Azure: Error during getting the instance type price:', url, e)
        return (-1.0, 'ERR: ' + str(e))

def getMinimalCheapPrice(inst_type):
    '''getPrice returns minimal Spot price'''
    return getPrice(inst_type, -1)[0]

from .Processor import Processor
from .Manager import Manager
from .Agent import Agent
from .Instance import Instance
