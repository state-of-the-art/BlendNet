from .InstanceProvider import InstanceProvider
from ..Workers import Workers

import os, importlib

modules = {}

with os.scandir(os.path.dirname(__file__)) as it:
    for entry in it:
        if not entry.is_dir() or entry.name.startswith('__'):
            continue
        print('INFO: Found provider "%s"' % entry.name)
        modules[entry.name] = importlib.import_module('.'+entry.name, __package__)

__all__ = [
    'Manager',
    'Agent',
]

selected_provider = 'local'

def selectProvider(provider):
    '''Sets the current provider identifier'''
    if provider not in modules:
        raise Exception('Unable to set unknown provider "%s"' % provider)
    global selected_provider
    selected_provider = provider

for name, module in modules.items():
    if name != 'local' and module.checkLocation():
        print('INFO: Importing manager/agent from "%s" provider' % name)
        global Manager, Agent
        Manager = importlib.import_module('.Manager', '%s.%s' % (__package__, name)).Manager
        Agent = importlib.import_module('.Agent', '%s.%s' % (__package__, name)).Agent
        selectProvider(name)
        break
else:
    print('INFO: Importing manager/agent from "local" provider')
    from .local import Manager, Agent


def getProvidersDoc():
    '''Return map with {ident: (name, desc), ...} of the providers'''
    out = {}
    for ident, module in modules.items():
        name, desc = module.__doc__.split('\n', 1)
        out[ident] = (name.strip(), desc.strip())

    return out

def getGoodProvidersList():
    '''Return a list with provider identifiers if their deps are ok'''
    return [name
            for name, module in modules.items()
            if name != 'local' and module.checkDependencies()] + ['local']

def _execProviderFunc(func, default = {}, *args, **kwargs):
    if not hasattr(modules[selected_provider], func):
        return default
    try:
        return getattr(modules[selected_provider], func)(*args, **kwargs)
    except:
        import sys
        print('WARN: Catched exception from "%s" provider execution of %s: %s' % (selected_provider, func, sys.exc_info()))
        return default

def getProviderInfo():
    '''Provides map with information about the provider'''
    return _execProviderFunc('getProviderInfo')

def getInstanceTypes():
    '''Provides map with information about the available instances'''
    return _execProviderFunc('getInstanceTypes')

def uploadFileToBucket(path, bucket, dest_path = None):
    '''Uploads file to the network storage'''
    return _execProviderFunc('uploadFileToBucket', None, path, bucket, dest_path)

def uploadDataToBucket(data, bucket, dest_path):
    '''Uploads data to the network storage'''
    return _execProviderFunc('uploadDataToBucket', None, data, bucket, dest_path)

def getResources(session_id):
    '''Returns map of allocated resources - manager and agents'''
    return _execProviderFunc('getResources', {}, session_id)

def getBucketName(session_id):
    return _execProviderFunc('getBucketName', None, session_id)

def getManagerName(session_id):
    return _execProviderFunc('getManagerName', 'blendnet-%s-manager' % session_id, session_id)

def getAgentNamePrefix(session_id):
    return _execProviderFunc('getAgentNamePrefix', 'blendnet-%s-agent-' % session_id, session_id)

def getManagerSizeDefault():
    return _execProviderFunc('getManagerSizeDefault', '')

def getAgentSizeDefault():
    return _execProviderFunc('getAgentSizeDefault', '')

def createInstanceManager(cfg):
    return _execProviderFunc('createInstanceManager', '', cfg)

def createInstanceAgent(cfg):
    return _execProviderFunc('createInstanceAgent', '', cfg)

def startInstance(name):
    return _execProviderFunc('startInstance', '', name)

def stopInstance(name):
    return _execProviderFunc('stopInstance', '', name)

def destroyInstance(name):
    return _execProviderFunc('destroyInstance', '', name)

def deleteInstance(name):
    return _execProviderFunc('deleteInstance', '', name)

def downloadDataFromBucket(bucket_name, path):
    return _execProviderFunc('downloadDataFromBucket', None, bucket_name, path)

def createFirewall(target_tag, port):
    return _execProviderFunc('createFirewall', None, target_tag, port)

def setupBucket(bucket_name, cfg):
    '''Creating the bucket and uploads the blendnet and configs into'''
    print('INFO: Uploading BlendNet logic to the bucket %s' % bucket_name)

    _execProviderFunc('createBucket', None, bucket_name)

    workers = Workers(
        'Uploading BlendNet logic to the bucket "%s"' % bucket_name,
        8,
        uploadFileToBucket,
    )

    # Walk through python files and upload them
    dirpath = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    for root, dirs, files in os.walk(dirpath):
        for f in files:
            if not f.endswith('.py'):
                continue
            filepath = os.path.join(root, f)
            workers.add(filepath, bucket_name, filepath.replace(dirpath, 'blendnet', 1))

    workers.start()

    import json
    uploadDataToBucket(json.dumps(cfg).encode('utf-8'), bucket_name, 'work_manager/manager.json')

    workers.wait()
