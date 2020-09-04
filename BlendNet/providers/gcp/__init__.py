'''Google Cloud Platform
Provide API access to allocate required resources in GCP
Dependencies: google cloud sdk installed and configured auth
Help: https://github.com/state-of-the-art/BlendNet/wiki/HOWTO:-Setup-provider:-Google-Cloud-Platform-(GCP)
'''

__all__ = [
    'Processor',
    'Manager',
    'Agent',
    'Instance',
]

import sys
import os.path
import time
import pathlib
import platform
import urllib.request
import subprocess

METADATA_URL = 'http://metadata.google.internal/computeMetadata/v1/'
METADATA_HEADER = ('Metadata-Flavor', 'Google')

LOCATION = None # If the script is running in the cloud
GOOGLE_CLOUD_SDK_ROOT = None
GOOGLE_CLOUD_SDK_CREDS = None
GOOGLE_CLOUD_SDK_CONFIGS = None

_PRICE_CACHE = { 'data':[], 'update': 0, 'usage': None }

def _requestMetadata(path):
    req = urllib.request.Request(METADATA_URL+path)
    req.add_header(*METADATA_HEADER)
    try:
        while True:
            with urllib.request.urlopen(req, timeout=2) as res:
                if res.getcode() == 503:
                    time.sleep(1)
                    continue
                return res.read().decode('utf-8')
    except:
        return None

def checkLocation():
    '''Returns True if it's the GCP environment'''
    global LOCATION

    if LOCATION is not None:
        return LOCATION

    LOCATION = _requestMetadata('') is not None
    return LOCATION

def setGoogleCloudSdk(path):
    global GOOGLE_CLOUD_SDK_ROOT
    if os.path.isdir(path) and os.path.isdir('%s/platform' % path):
        print('INFO: Found google cloud sdk: %s' % path)
        GOOGLE_CLOUD_SDK_ROOT = path
        return True

    return False

def findGoogleCloudSdk():
    '''Will try to find the google cloud sdk home directory'''
    # Windows doesn't use PATH to locate binary unless shell=True
    result = subprocess.run(['gcloud', 'info'],
                            shell=(platform.system() == 'Windows'),
                            stdout=subprocess.PIPE)

    if result.returncode != 0:
        return
    lines = result.stdout.decode('utf-8').split('\n')
    for line in lines:
        if not line.startswith('Installation Root: ['):
            continue
        path = line.strip()[:-1].lstrip('Installation Root: [')
        if setGoogleCloudSdk(path):
            return path

def loadGoogleCloudSdk():
    print('DEBUG: Loading gcloud paths')
    sys.path.append('%s/lib/third_party' % GOOGLE_CLOUD_SDK_ROOT)
    sys.path.append('%s/platform/bq/third_party' % GOOGLE_CLOUD_SDK_ROOT)
    sys.path.append('%s/lib' % GOOGLE_CLOUD_SDK_ROOT)

    # Init credentials and properties
    _getCreds()

def checkDependencies():
    return GOOGLE_CLOUD_SDK_ROOT is not None

def _getCreds():
    if not GOOGLE_CLOUD_SDK_ROOT:
        raise Exception("Unable to find the Google Cloud SDK - make sure it's installed, "
                        "gcloud utility is in the PATH and configured properly")

    global GOOGLE_CLOUD_SDK_CREDS
    if not GOOGLE_CLOUD_SDK_CREDS:
        from googlecloudsdk.core.credentials import store
        store.DevShellCredentialProvider().Register()
        store.GceCredentialProvider().Register()
        GOOGLE_CLOUD_SDK_CREDS = store.LoadIfEnabled()
    elif GOOGLE_CLOUD_SDK_CREDS.access_token_expired:
        print('DEBUG: Updating credentials token')
        from googlecloudsdk.core.credentials import store
        GOOGLE_CLOUD_SDK_CREDS = store.LoadIfEnabled()

    return GOOGLE_CLOUD_SDK_CREDS

def _getConfigs():
    global GOOGLE_CLOUD_SDK_CONFIGS
    if not GOOGLE_CLOUD_SDK_CONFIGS:
        from googlecloudsdk.core import properties
        props = properties.VALUES
        configs = {
            'account': props.core.account.Get(),
            'project': props.core.project.Get(),
            'region': props.compute.region.Get(),
            'zone': props.compute.zone.Get(),
        }

        if checkLocation():
            # Get defaults from metadata if they are not set
            if not configs['project']:
                configs['project'] = _requestMetadata('project/project-id')
            if not configs['zone']:
                configs['zone'] = _requestMetadata('instance/zone').rsplit('/', 1)[1]
            if not configs['region']:
                configs['region'] = configs['zone'].rsplit('-', 1)[0]

        GOOGLE_CLOUD_SDK_CONFIGS = configs

    return GOOGLE_CLOUD_SDK_CONFIGS

def _getCompute():
    creds = _getCreds()
    import googleapiclient.discovery
    return googleapiclient.discovery.build('compute', 'v1', credentials=creds)

def _getStorage():
    creds = _getCreds()
    import googleapiclient.discovery
    return googleapiclient.discovery.build('storage', 'v1', credentials=creds)

def _getBilling():
    creds = _getCreds()
    import googleapiclient.discovery
    return googleapiclient.discovery.build('cloudbilling', 'v1', credentials=creds)

def _getInstanceTypeInfo(name):
    '''Get info about the instance type'''
    try:
        compute, configs = _getCompute(), _getConfigs()
        resp = compute.machineTypes().get(project=configs['project'], zone=configs['zone'], machineType=name).execute()
        return { 'cpu': resp['guestCpus'], 'mem': resp['memoryMb'] }
    except:
        print('ERROR: Unable to get the GCP machine type info for:', name)

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
        if avail['project']['CPUS_ALL_REGIONS'] < manager_info['cpu']:
            errors.append('Available project CPUS_ALL_REGIONS is too small to provision the manager')
        if avail['region']['CPUS'] < manager_info['cpu']:
            errors.append('Available region CPUS is too small to provision the manager')
        if avail['project']['IN_USE_ADDRESSES'] < 1: # External addresses
            errors.append('Available project IN_USE_ADDRESSES is too small to provision the manager')
        if avail['region']['IN_USE_ADDRESSES'] < 1: # External addresses
            errors.append('Available region IN_USE_ADDRESSES is too small to provision the manager')
    else:
        errors.append('Unable to get the manager type info to validate quotas')

    # Disable cheap instances if preemptible cpus is not available
    if avail['region']['PREEMPTIBLE_CPUS'] < 1:
        errors.append('PREEMPTIBLE_CPUS is zero - cheap instances disabled')
        # TODO: Unify validation between providers
        # Required to get UI element disabled
        errors.append('Cheap instances not available')
        prefs.agent_use_cheap_instance = False

    # Agents
    if agents_info:
        if prefs.agent_use_cheap_instance:
            if avail['region']['PREEMPTIBLE_CPUS'] < agents_info['cpu'] * agents_num:
                errors.append('Available region PREEMPTIBLE_CPUS is too small to provision the agents')
        else:
            if avail['project']['CPUS_ALL_REGIONS'] < agents_info['cpu'] * agents_num + manager_info['cpu']:
                errors.append('Available project CPUS_ALL_REGIONS is too small to provision the agents')
            if avail['region']['CPUS'] < agents_info['cpu'] * agents_num + manager_info['cpu']:
                errors.append('Available region CPUS is too small to provision the agents')
    else:
        errors.append('Unable to get the agents type info to validate quotas')

    # Common
    if manager_info and agents_info:
        if avail['region']['INSTANCES'] < 1 + agents_num:
            errors.append('Available region INSTANCES is too small to provision the manager and agents')
    else:
        errors.append('Unable to get the manager and agents type info to validate quotas')

    if errors:
        errors.append('You can request GCP project quotas increase to get better experience')

    return errors

def getProviderInfo():
    configs = {}
    try:
        compute, configs = _getCompute(), _getConfigs()
        useful_quotas = [
            'CPUS',
            'CPUS_ALL_REGIONS',
            'DISKS_TOTAL_GB',
            'GLOBAL_INTERNAL_ADDRESSES',
            'INSTANCES',
            'IN_USE_ADDRESSES',
            'PREEMPTIBLE_CPUS',
        ]

        avail = {'project': {}, 'region': {}}

        # Get project quotas
        resp = compute.projects().get(project=configs['project']).execute()
        for q in resp['quotas']:
            if q['metric'] in useful_quotas:
                avail['project'][q['metric']] = q['limit'] - q['usage']
                configs['Project quota: %s' % q['metric']] = '%.1f, usage: %.1f' % (q['limit'], q['usage'])

        # Get region quotas
        resp = compute.regions().get(project=configs['project'], region=configs['region']).execute()
        for q in resp['quotas']:
            if q['metric'] in useful_quotas:
                avail['region'][q['metric']] = q['limit'] - q['usage']
                configs['Region quota: %s' % q['metric']] = '%.1f, usage: %.1f' % (q['limit'], q['usage'])

        errors = _verifyQuotas(avail)
        if errors:
            configs['ERRORS'] = errors
    except Exception as e:
        configs['ERRORS'] = ['Looks like access to the compute API is restricted '
                             '- please check your permissions: %s' % e]

    return configs

def getInstanceTypes():
    try:
        compute, configs = _getCompute(), _getConfigs()
        resp = compute.machineTypes().list(project=configs['project'], zone=configs['zone']).execute()
        return dict([ (d['name'], (d['description'], d['memoryMb']/1024.0)) for d in resp['items'] ])
    except:
        return {'ERROR': 'Looks like access to the compute API is restricted '
                         '- please check your permissions'}
    return {}

def _waitForOperation(compute, project, zone, operation):
    '''Waiting for compute operation to finish...'''
    while True:
        resp = compute.zoneOperations().get(project=project, zone=zone, operation=operation).execute()
        if resp['status'] == 'DONE':
            if 'error' in resp:
                raise Exception(resp['error'])
            return resp

        time.sleep(1)

def _getInstance(instance_name):
    '''Get the instance information or return None'''
    compute, configs = _getCompute(), _getConfigs()
    try:
        resp = compute.instances().get(project=configs['project'], zone=configs['zone'], instance=instance_name).execute()
        return resp
    except Exception:
        return None

def createInstanceManager(cfg):
    '''Creating a new instance for BlendNet Manager'''
    compute, configs = _getCompute(), _getConfigs()

    machine = 'zones/%s/machineTypes/%s' % (configs['zone'], cfg['instance_type'])
    # TODO: add option to specify the image to use
    #image_res = compute.images().getFromFamily(project='ubuntu-os-cloud', family='ubuntu-minimal-1804-lts').execute()
    image_res = compute.images().getFromFamily(project='debian-cloud', family='debian-10').execute()

    # TODO: make script overridable
    # TODO: too much hardcode here
    startup_script = '''#!/bin/sh
echo '--> Check for blender dependencies'
dpkg -l libxrender1 libxi6 libgl1
if [ $? -gt 0 ]; then
    apt update
    apt install --no-install-recommends -y libxrender1 libxi6 libgl1
fi

if [ ! -x /srv/blender/blender ]; then
    echo '--> Download & unpack blender'
    echo "{blender_sha256} -" > /tmp/blender.sha256
    curl -fLs "{blender_url}" | tee /tmp/blender.tar.bz2 | sha256sum -c /tmp/blender.sha256 || (echo "ERROR: checksum of the blender binary is incorrect"; exit 1)
    mkdir -p /srv/blender
    tar -C /srv/blender --strip-components=1 --checkpoint=10000 --checkpoint-action=echo='Unpacked %{{r}}T' -xf /tmp/blender.tar.bz2
fi

echo '--> Download & run the BlendNet manager'
adduser --shell /bin/false --disabled-password blendnet-user
gsutil -m cp -r 'gs://{project}-blendnet-{session_id}/work_manager/*' "$(getent passwd blendnet-user | cut -d: -f6)"
gsutil -m rm 'gs://{project}-blendnet-{session_id}/work_manager/**'
gsutil -m cp -r 'gs://{project}-blendnet-{session_id}/blendnet' /srv

cat <<'EOF' > /etc/systemd/system/blendnet-manager.service
[Unit]
Description=BlendNet Manager Service
After=network-online.target google-network-daemon.service

[Service]
User=blendnet-user
WorkingDirectory=~
Type=simple
ExecStart=/srv/blender/blender -b -noaudio -P /srv/blendnet/manager.py
Restart=always
TimeoutStopSec=60
StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl start blendnet-manager.service # We don't need "enable" here
    '''.format(
        blender_url=cfg['dist_url'],
        blender_sha256=cfg['dist_checksum'],
        project=configs['project'],
        session_id=cfg['session_id'],
    )
    #su -l -s /bin/sh -c '/srv/blender/blender -b -noaudio -P /srv/blendnet/manager.py' blendnet-user

    data = {
        'name': cfg['instance_name'],
        'machineType': machine,
        'minCpuPlatform': 'Intel Skylake', # Using the best option
        'description': 'BlendNet Agents Manager',
        'labels': {
            'app': 'blendnet',
            'type': 'manager',
            'session_id': cfg['session_id'],
        },
        'tags': { # TODO: add a way to specify custom tags
            'items': ['blendnet-manager']
        },
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {
                'sourceImage': image_res['selfLink'],
                'diskSizeGb': '200',
            },
        }],
        'networkInterfaces': [{
            'network': 'global/networks/default', # TODO: a way to specify network to use
            'accessConfigs': [{
                'type': 'ONE_TO_ONE_NAT', # Required here to allow easy connection from
                'name': 'External NAT',   # the Addon to monitor the activity and status
                'networkTier': 'PREMIUM', # TODO: add option to use only internal IPs
            }],
        }],
        'serviceAccounts': [{
            'email': 'default', # TODO: add a way to use specified service account
            'scopes': [
                'https://www.googleapis.com/auth/compute',
                'https://www.googleapis.com/auth/servicecontrol',
                'https://www.googleapis.com/auth/service.management.readonly',
                'https://www.googleapis.com/auth/logging.write',
                'https://www.googleapis.com/auth/monitoring.write',
                'https://www.googleapis.com/auth/trace.append',
                'https://www.googleapis.com/auth/devstorage.full_control',
            ],
        }],
        'metadata': {
            'items': [{
                'key': 'startup-script',
                'value': startup_script,
            }],
        },
    }

    # Creating an instance
    try:
        resp = compute.instances().insert(project=configs['project'], zone=configs['zone'], body=data).execute()

        # Waiting for the operation to complete
        resp = _waitForOperation(compute, configs['project'], configs['zone'], resp['id'])
    except Exception as e:
        print('WARN: Unable to create manager %s due to error: %s' % (cfg['instance_name'], str(e)))

    return cfg['instance_name']

def createInstanceAgent(cfg):
    '''Creating a new instance for BlendNet Agent'''

    compute, configs = _getCompute(), _getConfigs()
    # TODO: option to specify prefix/suffix for the name
    machine = 'zones/%s/machineTypes/%s' % (configs['zone'], cfg['instance_type'])
    # TODO: add option to specify the image to use
    #image_res = compute.images().getFromFamily(project='ubuntu-os-cloud', family='ubuntu-minimal-1804-lts').execute()
    image_res = compute.images().getFromFamily(project='debian-cloud', family='debian-10').execute()

    # TODO: make script overridable
    # TODO: too much hardcode here
    startup_script = '''#!/bin/sh
echo '--> Check for blender dependencies'
dpkg -l libxrender1 libxi6 libgl1
if [ $? -gt 0 ]; then
    apt update
    apt install --no-install-recommends -y libxrender1 libxi6 libgl1
fi

if [ ! -x /srv/blender/blender ]; then
    echo '--> Download & unpack blender'
    echo "{blender_sha256} -" > /tmp/blender.sha256
    curl -fLs "{blender_url}" | tee /tmp/blender.tar.bz2 | sha256sum -c /tmp/blender.sha256 || (echo "ERROR: checksum of the blender binary is incorrect"; exit 1)
    mkdir -p /srv/blender
    tar -C /srv/blender --strip-components=1 --checkpoint=10000 --checkpoint-action=echo='Unpacked %{{r}}T' -xf /tmp/blender.tar.bz2
fi

echo '--> Download & run the BlendNet agent'
adduser --shell /bin/false --disabled-password blendnet-user
gsutil -m cp -r 'gs://{project}-blendnet-{session_id}/work_{name}/*' "$(getent passwd blendnet-user | cut -d: -f6)"
gsutil -m cp -r 'gs://{project}-blendnet-{session_id}/blendnet' /srv

cat <<'EOF' > /etc/systemd/system/blendnet-agent.service
[Unit]
Description=BlendNet Agent Service
After=network-online.target google-network-daemon.service

[Service]
User=blendnet-user
WorkingDirectory=~
Type=simple
ExecStart=/srv/blender/blender -b -noaudio -P /srv/blendnet/agent.py
Restart=always
TimeoutStopSec=20
StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl start blendnet-agent.service # We don't need "enable" here
    '''.format(
        blender_url=cfg['dist_url'],
        blender_sha256=cfg['dist_checksum'],
        project=configs['project'],
        session_id=cfg['session_id'],
        name=cfg['instance_name'],
    )
    #su -l -s /bin/sh -c '/srv/blender/blender -b -noaudio -P /srv/blendnet/agent.py' blendnet-user

    data = {
        'name': cfg['instance_name'],
        'machineType': machine,
        'minCpuPlatform': 'Intel Skylake', # Using the best option
        'description': 'BlendNet Agent worker',
        'scheduling': {
            'preemptible': cfg['use_cheap_instance'],
        },
        'labels': {
            'app': 'blendnet',
            'type': 'agent',
            'session_id': cfg['session_id'],
        },
        'tags': { # TODO: add a way to specify custom tags
            'items': ['blendnet-agent'],
        },
        'disks': [{
            'boot': True,
            'autoDelete': True,
            'initializeParams': {
                'sourceImage': image_res['selfLink'],
                'diskSizeGb': '200',
            },
        }],
        'networkInterfaces': [{
            'network': 'global/networks/default', # TODO: a way to specify network to use
            'accessConfigs': [{
                'type': 'ONE_TO_ONE_NAT', # Here to allow to download the blender dependencies
                'name': 'External NAT',   # and will be removed by the Manager when agent will
                'networkTier': 'PREMIUM', # respond on the port with a proper status
            }],
        }],
        'serviceAccounts': [{
            'email': 'default', # TODO: add a way to use specified service account
            'scopes': [
                'https://www.googleapis.com/auth/devstorage.read_only',
                'https://www.googleapis.com/auth/logging.write',
                'https://www.googleapis.com/auth/monitoring.write',
                'https://www.googleapis.com/auth/servicecontrol',
                'https://www.googleapis.com/auth/service.management.readonly',
                'https://www.googleapis.com/auth/trace.append',
            ],
        }],
        'metadata': {
            'items': [{
                'key': 'startup-script',
                'value': startup_script,
            }],
        },
    }

    # Creating an instance
    try:
        resp = compute.instances().insert(project=configs['project'], zone=configs['zone'], body=data).execute()

        # Waiting for the operation to complete
        resp = _waitForOperation(compute, configs['project'], configs['zone'], resp['id'])
    except Exception as e:
        print('WARN: Unable to create agent %s due to error: %s' % (cfg['instance_name'], str(e)))

    return cfg['instance_name']

def removeInstanceExternalIP(instance_name):
    '''Will remove the external IP from the instance and return an internal one'''

    compute, configs = _getCompute(), _getConfigs()

    # Request the internal ip
    resp = _getInstance(instance_name)
    if not resp:
        return None

    ip = resp['networkInterfaces'][0]['networkIP']

    # Removing the external IP
    resp = compute.instances().deleteAccessConfig(
        project=configs['project'], zone=configs['zone'],
        instance=instance_name,
        accessConfig='External NAT',
        networkInterface='nic0'
    ).execute()

    # Waiting for the operation to complete
    resp = _waitForOperation(compute, configs['project'], configs['zone'], resp['id'])

    return ip

def startInstance(instance_name):
    '''Start stopped instance with specified name'''
    compute, configs = _getCompute(), _getConfigs()

    resp = compute.instances().start(project=configs['project'], zone=configs['zone'], instance=instance_name).execute()

    # Waiting for the operation to complete
    resp = _waitForOperation(compute, configs['project'], configs['zone'], resp['id'])

def stopInstance(instance_name):
    '''Stop instance with specified name'''
    compute, configs = _getCompute(), _getConfigs()

    resp = compute.instances().stop(project=configs['project'], zone=configs['zone'], instance=instance_name).execute()

    # Waiting for the operation to complete
    resp = _waitForOperation(compute, configs['project'], configs['zone'], resp['id'])

def deleteInstance(instance_name):
    '''Delete the instance with specified name'''
    compute, configs = _getCompute(), _getConfigs()

    resp = compute.instances().delete(project=configs['project'], zone=configs['zone'], instance=instance_name).execute()

    # Waiting for the operation to complete
    resp = _waitForOperation(compute, configs['project'], configs['zone'], resp['id'])

def createFirewall(target_tag, port):
    '''Create minimal firewall to access external IP of manager/agent'''
    # Skipping blendnet-agent
    if target_tag == 'blendnet-agent':
        return
    compute, configs = _getCompute(), _getConfigs()

    body = {
        'name': '%s-%d' % (target_tag, port),
        'network': 'global/networks/default',
        'direction': 'INGRESS',
        'description': 'Created by BlendNet to allow access to the service',
        'allowed': [{
            'IPProtocol': 'tcp',
            'ports': [str(port)],
        }],
        'sourceRanges': ['0.0.0.0/0'],
        'targetTags': [target_tag],
    }

    try:
        # TODO: wait for complete
        return compute.firewalls().insert(project=configs['project'], body=body).execute()
    except: # TODO: Check for the more specific exceptions
        return None

def _getBucket(bucket_name):
    '''Returns info about bucket or None'''
    storage = _getStorage()
    try:
        # TODO: handle issues with api unavailable or something
        return storage.buckets().get(bucket=bucket_name).execute()
    except: # TODO: be more specific here - exception could mean anything
        return None

def createBucket(bucket_name):
    '''Creates bucket if it's not exists'''
    storage, configs = _getStorage(), _getConfigs()

    if _getBucket(bucket_name):
        return True

    body = {
        'name': bucket_name,
        'location': configs['region'],
    }

    # TODO: handle issues with api unavailable
    storage.buckets().insert(project=configs['project'], body=body).execute()

    return True

def uploadFileToBucket(path, bucket_name, dest_path = None):
    '''Upload file to the bucket'''
    from googleapiclient.http import MediaIoBaseUpload
    storage = _getStorage()

    body = {
        'name': dest_path or path,
    }

    # if the plugin was called from a windows OS, we need to convert the path separators for gsutil
    if platform.system() == 'Windows':
        body['name'] = pathlib.PurePath(body['name']).as_posix()

    print('INFO: Uploading file to "gs://%s/%s"...' % (bucket_name, body['name']))
    with open(path, 'rb') as f:
        # TODO: make sure file uploaded or there is an isssue
        storage.objects().insert(
            bucket=bucket_name, body=body,
            media_body=MediaIoBaseUpload(f, 'application/octet-stream', chunksize=8*1024*1024),
        ).execute()

    return True

def uploadDataToBucket(data, bucket_name, dest_path):
    '''Upload file to the bucket'''
    from googleapiclient.http import MediaInMemoryUpload
    storage = _getStorage()

    body = {
        'name': dest_path,
    }

    # if the plugin was called from a windows OS, we need to convert the path separators for gsutil
    if platform.system() == 'Windows':
        body['name'] = pathlib.PurePath(body['name']).as_posix()

    print('INFO: Uploading data to "gs://%s/%s"...' % (bucket_name, body['name']))
    # TODO: make sure file uploaded or there is an isssue
    storage.objects().insert(
        bucket=bucket_name, body=body,
        media_body=MediaInMemoryUpload(data, mimetype='application/octet-stream'),
    ).execute()

    return True

def downloadDataFromBucket(bucket_name, path):
    from googleapiclient.http import MediaIoBaseDownload
    from io import BytesIO

    storage = _getStorage()

    print('INFO: Downloading data from "gs://%s/%s"...' % (bucket_name, path))
    req = storage.objects().get_media(bucket=bucket_name, object=path)
    data_fd = BytesIO()
    downloader = MediaIoBaseDownload(data_fd, req, chunksize=8*1024*1024)

    try:
        done = False
        while done is False:
            _, done = downloader.next_chunk()
    except Exception as e:
        print('WARN: Downloading failed: %s' % e)
        return None

    return data_fd.getvalue()

def getResources(session_id):
    '''Get the allocated resources with a specific session_id'''
    compute, configs = _getCompute(), _getConfigs()

    out = {'agents':{}}

    def parseInstanceInfo(it):
        access_cfgs = it['networkInterfaces'][0].get('accessConfigs', [{}])
        return {
            'id': it['name'],
            'name': it['name'],
            'ip': access_cfgs[0].get('natIP'),
            'internal_ip': it['networkInterfaces'][0].get('networkIP'),
            'type': it['machineType'].rsplit('/', 1)[1],
            'started': it['status'] == 'RUNNING',
            'stopped': it['status'] == 'TERMINATED',
            'created': it['creationTimestamp'],
        }

    req = compute.instances().list(
        project=configs['project'], zone=configs['zone'],
        filter='labels.session_id = "%s"' % session_id
    )

    while req is not None:
        resp = req.execute()
        for it in resp.get('items', []):
            inst = parseInstanceInfo(it)
            if it['labels'].get('type') == 'manager':
                out['manager'] = inst
            elif it['labels'].get('type') == 'agent':
                out['agents'][inst['name']] = inst
            else:
                print('WARN: Unknown resource instance %s' % inst['name'])

        req = compute.instances().list_next(previous_request=req, previous_response=resp)

    return out

def getNodeLog(instance_id):
    '''Get the instance serial output log'''
    compute, configs = _getCompute(), _getConfigs()

    resp = compute.instances().getSerialPortOutput(
        project=configs['project'], zone=configs['zone'],
        instance=instance_id, start=str(-256*1024), # Last 256KB
    ).execute()

    return resp.get('contents', '')

def getManagerSizeDefault():
    return 'n1-standard-1'

def getAgentSizeDefault():
    return 'n1-highcpu-2'

def getBucketName(session_id):
    '''Returns the appropriate bucket name'''
    configs = _getConfigs()
    return '%s-blendnet-%s' % (configs['project'], session_id.lower())

def getManagerName(session_id):
    return 'blendnet-%s-manager' % session_id

def getAgentsNamePrefix(session_id):
    return 'blendnet-%s-agent-' % session_id

def getCheapMultiplierList():
    '''GCP supports preemptible instances which are 0.3 price of regular instance'''
    return [ 0.3 ]

def getPrice(inst_type, cheap_multiplier):
    '''Returns the price of the instance type per hour for the current region'''
    global _PRICE_CACHE

    inst_info = _getInstanceTypeInfo(inst_type)
    if not inst_info:
        return (-1.0, 'ERR: Instance type not found')

    usage_type = 'OnDemand'
    if cheap_multiplier < 1.0:
        usage_type = 'Preemptible'

    desc_check = set()
    if inst_type == 'g1-small':
        desc_check.add('Small ')
    elif inst_type == 'f1-micro':
        desc_check.add('Micro ')
    elif inst_type.startswith('c2-'):
        desc_check.add('Compute optimized ')
    elif inst_type.startswith('m2-'):
        desc_check.add('Memory-Optimized ')
    else:
        desc_check.add(inst_type.split('-')[0].upper() + ' ')

    if _PRICE_CACHE['update'] < time.time() or _PRICE_CACHE['usage'] != usage_type:
        print('DEBUG: Update price cache')
        _PRICE_CACHE['data'] = []
        _PRICE_CACHE['usage'] = usage_type
        bill, configs = _getBilling(), _getConfigs()
        #req = bill.services().list() 'businessEntityName': 'businessEntities/GCP' = 'services/6F81-5844-456A'
        req = bill.services().skus().list(parent='services/6F81-5844-456A')
        while req is not None:
            resp = req.execute()
            for it in resp.get('skus', []):
                if configs['region'] not in it.get('serviceRegions', []):
                    continue
                if it.get('category', {}).get('usageType') != usage_type:
                    continue
                if it.get('category', {}).get('resourceFamily') in ('Network', 'Storage'):
                    continue
                if it.get('category', {}).get('resourceGroup') in ('GPU',):
                    continue
                if 'Custom ' in it.get('description') or 'Sole Tenancy ' in it.get('description'):
                    continue
                if ' Premium ' in it.get('description'):
                    continue
                _PRICE_CACHE['data'].append(it)
            req = bill.services().skus().list_next(previous_request=req, previous_response=resp)

        print('DEBUG: Updated price cache: ' + str(len(_PRICE_CACHE['data'])))
        _PRICE_CACHE['update'] = time.time() + 60*60

    out_price = 0
    out_currency = 'NON'

    for it in _PRICE_CACHE['data']:
        if not all([ check in it.get('description') for check in desc_check ]):
            continue
        exp = it.get('pricingInfo', [{}])[0].get('pricingExpression', {})
        price_def = exp.get('tieredRates', [{}])[0].get('unitPrice', {})
        price = float(price_def.get('unit', '0')) + price_def.get('nanos', 0)/1000000000.0
        out_currency = price_def.get('currencyCode')
        if ' Core ' in it.get('description'):
            print('DEBUG: Price adding CPU: ' + str(price * inst_info['cpu']))
            out_price += price * inst_info['cpu']
        elif ' Ram ' in it.get('description'):
            print('DEBUG: Price adding MEM: ' + str(price * (inst_info['mem'] / 1024.0)))
            out_price += price * (inst_info['mem'] / 1024.0)

    return (out_price, out_currency)

findGoogleCloudSdk()

if GOOGLE_CLOUD_SDK_ROOT:
    loadGoogleCloudSdk()

from .Processor import Processor
from .Manager import Manager
from .Agent import Agent
from .Instance import Instance
