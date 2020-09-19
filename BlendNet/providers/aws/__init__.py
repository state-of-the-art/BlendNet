'''Amazon Web Services
Provide API access to allocate required resources in AWS
Dependencies: aws cli v2
Help: https://github.com/state-of-the-art/BlendNet/wiki/HOWTO:-Setup-provider:-Amazon-Web-Services-(AWS)
'''

__all__ = [
    'Processor',
    'Manager',
    'Agent',
    'Instance',
]

# Exception to notify that the command returned exitcode != 0
class AwsToolException(Exception):
    pass

import os
import sys
import json
import platform
import tempfile
import ssl
import site
import urllib.request
import subprocess
import pathlib

METADATA_URL = 'http://169.254.169.254/latest/'

LOCATION = None # If the script is running in the cloud
AWS_TOOL_PATH = None
AWS_EXEC_PREFIX = ('--output', 'json')
AWS_CONFIGS = None

def _requestMetadata(path, verbose = False):
    req = urllib.request.Request(METADATA_URL+path)
    try:
        while True:
            with urllib.request.urlopen(req, timeout=2) as res:
                if res.getcode() == 503:
                    print('WARN: Unable to reach metadata serivce')
                    time.sleep(5)
                    continue
                return res.read().decode('utf-8')
    except Exception as e:
        if verbose:
            print('WARN: Metadata is not available ' + path)
        return None

def checkLocation():
    '''Returns True if it's the GCP environment'''
    global LOCATION

    if LOCATION is not None:
        return LOCATION

    LOCATION = _requestMetadata('', True) is not None
    return LOCATION

def checkDependencies():
    return AWS_TOOL_PATH is not None

def _executeAwsTool(*args, data=None):
    '''Runs the aws tool and returns code and data as tuple, data will be sent to stdin as bytes'''
    to_run = AWS_EXEC_PREFIX
    if args[0] == 's3' and '--region' in AWS_EXEC_PREFIX:
        to_run = to_run[:-2]
    result = subprocess.run(to_run + args,
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise AwsToolException('AWS tool returned %d during execution of "%s": %s' % (
            result.returncode, AWS_EXEC_PREFIX + args, result.stderr))

    data = None
    try:
        data = json.loads(result.stdout)
    except json.decoder.JSONDecodeError:
        pass

    return data

def findAWSTool():
    '''Finds absolute path of the aws tool'''
    paths = os.environ['PATH'].split(os.pathsep)
    executable = 'aws'
    extlist = {''}

    if platform.system() == 'Windows':
        extlist = set(os.environ['PATHEXT'].lower().split(os.pathsep))

    for ext in extlist:
        execname = executable + ext
        for p in paths:
            f = os.path.join(p, execname)
            if os.path.isfile(f):
                global AWS_TOOL_PATH, AWS_EXEC_PREFIX
                AWS_TOOL_PATH = f
                AWS_EXEC_PREFIX = (AWS_TOOL_PATH,) + AWS_EXEC_PREFIX
                print('INFO: Found aws tool: ' + AWS_TOOL_PATH)
                configs = _getConfigs()
                if 'region' in configs:
                    print('INFO: Set region for aws tool: ' + configs['region'])
                    AWS_EXEC_PREFIX += ('--region', configs['region'])
                return

def _getConfigs():
    '''Returns dict with aws tool configs'''
    global AWS_CONFIGS
    if not AWS_CONFIGS:
        configs = dict()
        # aws configure returns non-json table, so using direct call
        result = subprocess.run([AWS_TOOL_PATH, 'configure', 'list'], stdout=subprocess.PIPE)
        if result.returncode != 0:
            print('ERROR: Unable to get aws config: %s %s' % (result.returncode, result.stdout))
            return configs

        data = result.stdout.decode('UTF-8').strip()
        for line in data.split(os.linesep)[2:]:
            param = line.split()[0]
            result = subprocess.run([AWS_TOOL_PATH, 'configure', 'get', param], stdout=subprocess.PIPE)
            if result.returncode == 0:
                configs[param] = result.stdout.decode('UTF-8').strip()

        if checkLocation():
            print('INFO: Receiving configuration from the instance metadata')
            json_data = _requestMetadata('dynamic/instance-identity/document')
            data = None
            if json_data is not None:
                try:
                    data = json.loads(json_data)
                except json.decoder.JSONDecodeError:
                    print('ERROR: Unable to parse the instance json metadata: %s' % json_data)
                    pass

            if data is not None:
                configs['region'] = configs.get('region', data['region'])

        AWS_CONFIGS = configs

    return AWS_CONFIGS


def getProviderInfo():
    configs = dict()
    try:
        configs = _getConfigs()
        useful_quotas = {
            'Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances': 'Std instances',
            'Running On-Demand F instances': 'F instances',
            'Running On-Demand G instances': 'G instances',
            'Running On-Demand Inf instances': 'Inf instances',
            'Running On-Demand P instances': 'P instances',
            'Running On-Demand X instances': 'X instances',
        }

        # Get quotas
        data = _executeAwsTool('service-quotas', 'list-service-quotas',
                               '--service-code', 'ec2', '--query', 'Quotas[].[QuotaName, Value]')

        for q in data:
            if q[0] in useful_quotas:
                configs['Quota: ' + useful_quotas[q[0]]] = '%.1f' % (q[1],)

    except AwsToolException as e:
        configs['ERRORS'] = ['Looks like access to the API is restricted '
                             '- please check your permissions: %s' % e]

    return configs

def getInstanceTypes():
    try:
        data = _executeAwsTool('ec2', 'describe-instance-types',
                               '--query', 'InstanceTypes[].[InstanceType, VCpuInfo.DefaultVCpus, MemoryInfo.SizeInMiB] | sort_by(@, &[0])')
        return dict([ (d[0], ('%s vCPUs %s GB RAM' % (d[1], d[2]/1024.0), d[2]/1024.0)) for d in data ])
    except AwsToolException as e:
        return {'ERROR': 'Looks like access to the API is restricted '
                         '- please check your permissions: %s' % e}
    return {}

def _createRoles():
    '''Will ensure the required roles are here'''
    role_doc = {
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Service":"ec2.amazonaws.com"
            },
            "Action":"sts:AssumeRole",
        }],
    }

    # Create blendnet-agent role
    try:
        _executeAwsTool('iam', 'create-role',
                        '--role-name', 'blendnet-agent',
                        '--description', 'Automatically created by BlendNet',
                        '--assume-role-policy-document', json.dumps(role_doc))
        _executeAwsTool('iam', 'wait', 'role-exists',
                        '--role-name', 'blendnet-agent')
        print('INFO: Creating the instance profile for role blendnet-agent')
        _executeAwsTool('iam', 'attach-role-policy',
                        '--role-name', 'blendnet-agent',
                        '--policy-arn', 'arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess')
        _executeAwsTool('iam', 'create-instance-profile',
                        '--instance-profile-name', 'blendnet-agent')
        _executeAwsTool('iam', 'add-role-to-instance-profile',
                        '--instance-profile-name', 'blendnet-agent',
                        '--role-name', 'blendnet-agent')
        _executeAwsTool('iam', 'wait', 'instance-profile-exists',
                        '--instance-profile-name', 'blendnet-agent')
    except AwsToolException:
        # The blendnet-agent role is already exists
        pass

    # Create blendnet-manager role
    try:
        _executeAwsTool('iam', 'create-role',
                        '--role-name', 'blendnet-manager',
                        '--description', 'Automatically created by BlendNet',
                        '--assume-role-policy-document', json.dumps(role_doc))
        print('INFO: Creating the instance profile for role blendnet-manager')
        _executeAwsTool('iam', 'wait', 'role-exists',
                        '--role-name', 'blendnet-manager')
        # Those perms could be neared down - but I think it's too much for now
        _executeAwsTool('iam', 'attach-role-policy',
                        '--role-name', 'blendnet-manager',
                        '--policy-arn', 'arn:aws:iam::aws:policy/AmazonEC2FullAccess')
        _executeAwsTool('iam', 'attach-role-policy',
                        '--role-name', 'blendnet-manager',
                        '--policy-arn', 'arn:aws:iam::aws:policy/AmazonS3FullAccess')
        # Allow blendnet-manager to use blendnet-agent instance profile and role
        agent_instance_profile = _executeAwsTool('iam', 'get-instance-profile',
                                                 '--instance-profile-name', 'blendnet-agent',
                                                 '--query', 'InstanceProfile')
        policy_doc = {
            "Statement": [{
                "Effect": "Allow",
                "Action": "iam:PassRole",
                "Resource": [
                    agent_instance_profile['Arn'],
                    agent_instance_profile['Roles'][0]['Arn'],
                ],
            }],
        }
        _executeAwsTool('iam', 'put-role-policy',
                        '--role-name', 'blendnet-manager',
                        '--policy-name', 'allow_use_blendnet-agent',
                        '--policy-document', json.dumps(policy_doc))
        _executeAwsTool('iam', 'create-instance-profile',
                        '--instance-profile-name', 'blendnet-manager')
        _executeAwsTool('iam', 'add-role-to-instance-profile',
                        '--instance-profile-name', 'blendnet-manager',
                        '--role-name', 'blendnet-manager')
        _executeAwsTool('iam', 'wait', 'instance-profile-exists',
                        '--instance-profile-name', 'blendnet-manager')
        # If it's not wait - we will see the next error during manager allocation
        # Value (blendnet-manager) for parameter iamInstanceProfile.name is invalid. Invalid IAM Instance Profile name
        time.sleep(30)
    except AwsToolException:
        # The blendnet-manager role is already exists
        pass

def _getImageAmi(name = 'debian-10-amd64-daily-*'):
    '''Gets the latest image per name filter'''
    data = _executeAwsTool('ec2', 'describe-images',
                           '--filters', json.dumps([{'Name':'name','Values': [name]}]),
                           '--query', 'sort_by(Images, &CreationDate)[].[Name,ImageId,BlockDeviceMappings[0].DeviceName][-1]')
    print('INFO: Got image %s' % (data[1],))
    return (data[1], data[2])

def _getInstanceId(instance_name):
    '''Gets the instance id based on the tag Name'''
    data = _executeAwsTool('ec2', 'describe-instances',
                           '--filters', json.dumps([
                              {'Name':'tag:Name','Values': [instance_name]},
                              {'Name':'instance-state-name','Values': ['pending','running','shutting-down','stopping','stopped']},
                           ]),
                           '--query', 'Reservations[].Instances[].InstanceId')
    if len(data) != 1:
        raise AwsToolException('Error in request of unique instance id with name "%s": %s' % (instance_name, data))

    return data[0]

def createInstanceManager(cfg):
    '''Creating a new instance for BlendNet Manager'''

    _createRoles()

    try:
        inst_id = _getInstanceId(cfg['instance_name'])
        # If it pass here - means the instance is already existing
        return inst_id
    except AwsToolException:
        # No instance existing - than we can proceed
        pass

    image = _getImageAmi()
    disk_config = [{
        'DeviceName': image[1],
        'Ebs': {
            'DeleteOnTermination': True,
            'VolumeSize': 200,
            'VolumeType': 'standard',
        },
    }]

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

cat <<'EOF' > /usr/local/bin/blendnet_cloud_init.sh
#!/bin/sh
echo '--> Update the BlendNet manager'
aws s3 cp --recursive 's3://blendnet-{session_id}/work_manager' "$(getent passwd blendnet-user | cut -d: -f6)"
aws s3 rm --recursive 's3://blendnet-{session_id}/work_manager'
aws s3 cp --recursive 's3://blendnet-{session_id}/blendnet' /srv/blendnet
EOF

chmod +x /usr/local/bin/blendnet_cloud_init.sh
adduser --shell /bin/false --disabled-password blendnet-user

cat <<'EOF' > /etc/systemd/system/blendnet-manager.service
[Unit]
Description=BlendNet Manager Service
After=network-online.target google-network-daemon.service

[Service]
PermissionsStartOnly=true
User=blendnet-user
WorkingDirectory=~
Type=simple
ExecStartPre=/usr/local/bin/blendnet_cloud_init.sh
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
    )

    options = [
        'ec2', 'run-instances',
        '--tag-specifications', 'ResourceType=instance,Tags=['
            '{Key=Name,Value=%s},'
            '{Key=Session,Value=%s},'
            '{Key=Type,Value=manager}]' % (cfg['instance_name'], cfg['session_id']),
        '--image-id', image[0],
        '--instance-type', cfg['instance_type'],
        '--iam-instance-profile', '{"Name":"blendnet-manager"}',
        '--block-device-mappings', json.dumps(disk_config),
        #'--key-name', 'default_key', # If you want to ssh to the instance (change createFirewall func too)
        '--security-groups', 'blendnet-manager',
        '--user-data', startup_script,
    ]

    # Creating an instance
    print('INFO: Creating manager %s' % (cfg['instance_name'],))
    data = _executeAwsTool(*options)
    # Waiting for the operation to completed
    _executeAwsTool('ec2', 'wait', 'instance-running',
                    '--instance-ids', data['Instances'][0]['InstanceId'])

    return data['Instances'][0]['InstanceId']

def createInstanceAgent(cfg):
    '''Creating a new instance for BlendNet Agent'''

    try:
        inst_id = _getInstanceId(cfg['instance_name'])
        # If it pass here - means the instance is already existing
        return inst_id
    except AwsToolException:
        # No instance existing - than we can proceed
        pass

    image = _getImageAmi()
    disk_config = [{
        'DeviceName': image[1],
        'Ebs': {
            'DeleteOnTermination': True,
            'VolumeSize': 200,
            'VolumeType': 'standard',
        },
    }]

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

cat <<'EOF' > /usr/local/bin/blendnet_cloud_init.sh
#!/bin/sh
echo '--> Update the BlendNet agent'
aws s3 cp --recursive 's3://blendnet-{session_id}/work_{name}' "$(getent passwd blendnet-user | cut -d: -f6)"
aws s3 cp --recursive 's3://blendnet-{session_id}/blendnet' /srv/blendnet
EOF

chmod +x /usr/local/bin/blendnet_cloud_init.sh
adduser --shell /bin/false --disabled-password blendnet-user

cat <<'EOF' > /etc/systemd/system/blendnet-agent.service
[Unit]
Description=BlendNet Agent Service
After=network-online.target google-network-daemon.service

[Service]
PermissionsStartOnly=true
User=blendnet-user
WorkingDirectory=~
Type=simple
ExecStartPre=/usr/local/bin/blendnet_cloud_init.sh
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
        session_id=cfg['session_id'],
        name=cfg['instance_name'],
    )

    options = [
        'ec2', 'run-instances',
        '--tag-specifications', 'ResourceType=instance,Tags=['
            '{Key=Name,Value=%s},'
            '{Key=Session,Value=%s},'
            '{Key=Type,Value=agent}]' % (cfg['instance_name'], cfg['session_id']),
        '--image-id', image[0],
        '--instance-type', cfg['instance_type'],
        '--iam-instance-profile', '{"Name":"blendnet-agent"}',
        '--block-device-mappings', json.dumps(disk_config),
        #'--key-name', 'default_key', # If you want to ssh to the instance (change createFirewall func too)
        '--security-groups', 'blendnet-agent',
        '--user-data', startup_script,
    ]

    if cfg['use_cheap_instance']:
        # Running in the cheapest zone
        zone_prices = _getZonesMinimalSpotPrice(cfg['instance_type'])
        (min_price_zone, min_price) = zone_prices.popitem()
        for zone in zone_prices:
            if zone_prices[zone] < min_price:
                min_price = zone_prices[zone]
                min_price_zone = zone
        print('INFO: Running cheap agent instance with max price %f in zone %s (min %f)' % (
            cfg['instance_max_price'],
            min_price_zone, min_price,
        ))
        options.append('--placement')
        options.append(json.dumps({
            'AvailabilityZone': min_price_zone,
        }))
        options.append('--instance-market-options')
        options.append(json.dumps({
            'MarketType': 'spot',
            'SpotOptions': {
                'MaxPrice': str(cfg['instance_max_price']),
                'SpotInstanceType': 'one-time',
            },
        }))

    # Creating an instance
    print('INFO: Creating agent %s' % (cfg['instance_name'],))
    data = _executeAwsTool(*options)
    # Waiting for the operation to completed
    _executeAwsTool('ec2', 'wait', 'instance-running',
                    '--instance-ids', data['Instances'][0]['InstanceId'])

    return data['Instances'][0]['InstanceId']

def startInstance(instance_id):
    '''Start stopped instance with specified name'''

    _executeAwsTool('ec2', 'start-instances',
                    '--instance-ids', instance_id)
    # Waiting for the operation to completed
    _executeAwsTool('ec2', 'wait', 'instance-running',
                    '--instance-ids', instance_id)

def _isInstanceSpot(instance_id):
    '''Gets the instance is in spot lifecycle'''
    data = _executeAwsTool('ec2', 'describe-instances',
                           '--instance-ids', instance_id,
                           '--query', 'Reservations[].Instances[].InstanceLifecycle')
    if len(data) == 0:
        return False
    elif len(data) > 1:
        raise AwsToolException('Error in request of instance lifecycle for "%s": %s' % (instance_id, data))

    return data[0] == 'spot'

def stopInstance(instance_id):
    '''Stop instance with specified name'''

    # Check spot instance, it can't be stopped - only deleted
    if _isInstanceSpot(instance_id):
        deleteInstance(instance_id)
        return

    _executeAwsTool('ec2', 'stop-instances',
                    '--instance-ids', instance_id)
    # Waiting for the operation to completed
    _executeAwsTool('ec2', 'wait', 'instance-stopped',
                    '--instance-ids', instance_id)

def deleteInstance(instance_id):
    '''Delete the instance with specified name'''

    _executeAwsTool('ec2', 'terminate-instances',
                    '--instance-ids', instance_id)
    # Waiting for the operation to completed
    _executeAwsTool('ec2', 'wait', 'instance-terminated',
                    '--instance-ids', instance_id)

def createFirewall(target_group, port):
    '''Create minimal firewall to access external IP of manager/agent'''

    # Create the security group
    try:
        _executeAwsTool('ec2', 'create-security-group',
                        '--group-name', target_group,
                        '--description', 'Automatically created by BlendNet')
        print('INFO: Creating security group for %s' % (target_group,))
        # Rule to allow remote ssh to the instance
        # if you enable it don't forget to remove the blendnet sec groups from AWS to recreate them
        #_executeAwsTool('ec2', 'authorize-security-group-ingress',
        #                '--group-name', target_group,
        #                '--protocol', 'tcp',
        #                '--port', '22',
        #                '--cidr', '0.0.0.0/0')
        _executeAwsTool('ec2', 'authorize-security-group-ingress',
                        '--group-name', target_group,
                        '--protocol', 'tcp',
                        '--port', str(port),
                        '--cidr', '172.0.0.0/8' if target_group == 'blendnet-agent' else '0.0.0.0/0')
        # Waiting for the operation to completed
        _executeAwsTool('ec2', 'wait', 'security-group-exists',
                        '--group-names', target_group)
    except AwsToolException:
        # The blendnet-manager security group already exists
        pass

def createBucket(bucket_name):
    '''Creates bucket if it's not exists'''

    _executeAwsTool('s3', 'mb', 's3://' + bucket_name)

    return True

def uploadFileToBucket(path, bucket_name, dest_path = None):
    '''Upload file to the bucket'''

    if not dest_path:
        dest_path = path

    # If the plugin was called from Windows, we need to convert the path separators
    if platform.system() == 'Windows':
        dest_path = pathlib.PurePath(dest_path).as_posix()

    dest_path = 's3://%s/%s' % (bucket_name, dest_path)

    print('INFO: Uploading file to "%s" ...' % (dest_path,))
    _executeAwsTool('s3', 'cp', path, dest_path)

    return True

def uploadDataToBucket(data, bucket_name, dest_path):
    '''Upload data to the bucket'''
    # WARN: tmpfile is not allowed to use by subprocesses on Win

    dest_path = 's3://%s/%s' % (bucket_name, dest_path)

    print('INFO: Uploading data to "%s" ...' % (dest_path,))
    _executeAwsTool('s3', 'cp', '-', dest_path, data=data)

    return True

def downloadDataFromBucket(bucket_name, path):
    tmp_file = tempfile.NamedTemporaryFile()

    path = 's3://%s/%s' % (bucket_name, path)

    print('INFO: Downloading file from "%s" ...' % (path,))

    try:
        _executeAwsTool('s3', 'cp', path, tmp_file.name)
    except AwsToolException:
        print('WARN: Downloading failed')
        return None

    # The original tmp_file is unlinked, so reread it
    with open(tmp_file.name, 'rb') as fh:
        return fh.read()

def getResources(session_id):
    '''Get the allocated resources with a specific session_id'''
    out = {'agents':{}}

    def parseInstanceInfo(it):
        try:
            name = [ tag['Value'] for tag in it['Tags'] if tag['Key'] == 'Name' ][0]
            return {
                'id': it.get('InstanceId'),
                'name': name,
                'ip': it.get('PublicIpAddress'),
                'internal_ip': it['PrivateIpAddress'],
                'type': it['InstanceType'],
                'started': it['State']['Name'] == 'running',
                'stopped': it['State']['Name'] == 'stopped',
                'created': it['LaunchTime'],
            }
        except:
            return None

    data = _executeAwsTool('ec2', 'describe-instances',
                           '--filters', json.dumps([
                              {'Name':'tag:Session','Values': [session_id]},
                              {'Name':'instance-state-name','Values': ['pending','running','shutting-down','stopping','stopped']},
                           ]),
                           '--query', 'Reservations[].Instances[]')

    for it in data:
        inst = parseInstanceInfo(it)
        if not inst:
            continue
        it_type = [ tag['Value'] for tag in it['Tags'] if tag['Key'] == 'Type' ][0]
        if it_type == 'manager':
            out['manager'] = inst
        elif it_type == 'agent':
            out['agents'][inst['name']] = inst
        else:
            print('WARN: Unknown type resource instance %s' % inst['name'])

    return out

def getNodeLog(instance_id):
    '''Get the instance serial output log'''
    data = _executeAwsTool('ec2', 'get-console-output',
                           '--instance-id', instance_id)

    return data.get('Output', '')

def getManagerSizeDefault():
    return 't2.micro'

def getAgentSizeDefault():
    return 't2.micro'

def getBucketName(session_id):
    '''Returns the appropriate bucket name'''
    return 'blendnet-%s' % (session_id.lower(),)

def getManagerName(session_id):
    return 'blendnet-%s-manager' % session_id

def getAgentsNamePrefix(session_id):
    return 'blendnet-%s-agent-' % session_id

def getCheapMultiplierList():
    '''AWS supports spot instances which is market based on spot price'''
    return [0.33] + [ i/100.0 for i in range(1, 100) ]

def getPrice(inst_type, cheap_multiplier):
    '''Returns the price of the instance type per hour for the current region'''
    configs = _getConfigs()

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

    url = 'https://a0.p.awsstatic.com/pricing/1.0/ec2/region/%s/ondemand/linux/index.json' % (configs['region'],)
    req = urllib.request.Request(url)
    try:
        while True:
            with urllib.request.urlopen(req, timeout=5, context=ctx) as res:
                if res.getcode() == 503:
                    print('WARN: Unable to reach price url')
                    time.sleep(5)
                    continue
                data = json.load(res)
                for d in data['prices']:
                    if d['attributes']['aws:ec2:instanceType'] == inst_type:
                        return (float(list(d['price'].values())[0]) * cheap_multiplier, list(d['price'].keys())[0])
                return (-1.0, 'ERR: Unable to find the price')
    except Exception as e:
        print('WARN: Error during getting the instance type price:', url, e)
        return (-1.0, 'ERR: ' + str(e))

def _getZonesMinimalSpotPrice(inst_type):
    '''Returns the minimal spot price for instance type per zone'''
    data = _executeAwsTool('ec2', 'describe-spot-price-history',
                           '--instance-types', json.dumps([inst_type]),
                           '--product-descriptions', json.dumps(['Linux/UNIX']),
                           '--query', 'SpotPriceHistory[]')
    min_prices = dict()
    for it in data:
        # First items in the list is latest
        if it['AvailabilityZone'] not in min_prices:
            min_prices[it['AvailabilityZone']] = float(it['SpotPrice'])

    return min_prices

def getMinimalCheapPrice(inst_type):
    '''Will check the spot history and retreive the latest minimal price'''
    return min(_getZonesMinimalSpotPrice(inst_type).values())

findAWSTool()

from .Processor import Processor
from .Manager import Manager
from .Agent import Agent
from .Instance import Instance
