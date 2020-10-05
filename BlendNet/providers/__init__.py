from .InstanceProvider import InstanceProvider
from ..Workers import Workers

import os
import traceback
import importlib
import platform

__all__ = [
    'Processor',
    'Manager',
    'Agent',
]

modules = {}
modules_messages = {}

with os.scandir(os.path.dirname(__file__)) as it:
    for entry in it:
        if not entry.is_dir() or entry.name.startswith('__'):
            continue
        print('INFO: Found provider "%s"' % entry.name)
        modules[entry.name] = None

selected_provider = 'local'

def selectProvider(provider):
    '''Sets the current provider identifier'''
    if provider not in modules:
        raise Exception('Unable to set unknown provider "%s"' % provider)

    # Check the provider is loaded or contains an error
    if not modules.get(provider) or isinstance(modules.get(provider), str):
        try:
            modules[provider] = importlib.import_module('.'+provider, __package__)
        except Exception as e:
            print('WARN: Unable to load "%s" provider due to init error: %s' % (provider, e))
            #traceback.print_exc()
            modules[provider] = 'ERROR: Unable to load provider: %s' % (e,)

    if isinstance(modules[provider], str):
        print('WARN: Unable to select "%s" provider due to loading error: %s' % (provider, modules[provider]))
        return

    check = modules[provider].checkDependencies()
    if isinstance(check, str):
        print('WARN: Unable to select "%s" provider due to dependency error: %s' % (provider, check))
        modules_messages[provider] = [check]
        return
    modules_messages[provider] = []

    print('INFO: Importing base from "%s" provider' % (provider,))
    global Processor, Manager, Agent
    Processor = importlib.import_module('.Processor', '%s.%s' % (__package__, provider)).Processor
    Manager = importlib.import_module('.Manager', '%s.%s' % (__package__, provider)).Manager
    Agent = importlib.import_module('.Agent', '%s.%s' % (__package__, provider)).Agent

    global selected_provider
    selected_provider = provider

    return True

def getProviderMessages(provider):
    '''Returns messages happening in the provider module'''
    return modules_messages.get(provider, [])

def getProvidersDoc():
    '''Return map with {ident: (name, desc), ...} of the providers'''
    out = {}
    for ident, module in modules.items():
        if module is None:
            out[ident] = (ident + ' - select to init provider', '')
            continue
        elif isinstance(module, str):
            out[ident] = (ident + ' - ERROR: unable to initialize', module)
            continue
        name, desc = module.__doc__.split('\n', 1)
        out[ident] = (name.strip(), desc.strip())

    return out

def isProviderGood(name):
    '''Return a list with provider identifiers if their deps are ok'''
    return modules[name] is not None and not isinstance(modules[name], str)

def _execProviderFunc(func, default = {}, *args, **kwargs):
    if modules[selected_provider] is None or not hasattr(modules[selected_provider], func):
        return default
    try:
        return getattr(modules[selected_provider], func)(*args, **kwargs)
    except Exception as e:
        print('WARN: Catched exception from "%s" provider execution of %s: %s' % (selected_provider, func, e))
        import traceback
        traceback.print_exc()
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
    # Agents are stored with the name keys
    return _execProviderFunc('getResources', {'agents':{}}, session_id)

def getNodeLog(instance_id):
    '''Returns string with the node serial output log'''
    return _execProviderFunc('getNodeLog', 'NOT IMPLEMENTED', instance_id)

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
    ''' Returns created instance id '''
    return _execProviderFunc('createInstanceManager', '', cfg)

def createInstanceAgent(cfg):
    ''' Returns created instance id '''
    return _execProviderFunc('createInstanceAgent', '', cfg)

def startInstance(inst_id):
    return _execProviderFunc('startInstance', '', inst_id)

def stopInstance(inst_id):
    return _execProviderFunc('stopInstance', '', inst_id)

def destroyInstance(inst_id):
    return _execProviderFunc('destroyInstance', '', inst_id)

def deleteInstance(inst_id):
    return _execProviderFunc('deleteInstance', '', inst_id)

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
    for root, _, files in os.walk(dirpath):
        for f in files:
            if not f.endswith('.py'):
                continue
            filepath = os.path.join(root, f)
            workers.add(filepath, bucket_name, filepath.replace(dirpath, 'blendnet', 1))

    workers.start()

    import json
    uploadDataToBucket(json.dumps(cfg).encode('utf-8'), bucket_name, 'work_manager/manager.json')

    workers.wait()

def getCheapMultiplierList():
    '''Returns the list of available multipliers to get the right price'''
    return _execProviderFunc('getCheapMultiplierList', [])

def getPrice(inst_type, cheap_multiplier):
    '''Return the price of the instance type per hour'''
    return _execProviderFunc('getPrice', (-1.0, 'ERR'), inst_type, cheap_multiplier)

def getMinimalCheapPrice(inst_type):
    '''Finds the lowest available instance price and returns it'''
    return _execProviderFunc('getMinimalCheapPrice', -1.0, inst_type)

def findPATHExec(executable):
    '''Finds absolute path of the required executable'''
    paths = os.environ['PATH'].split(os.pathsep)
    extlist = {''}

    if platform.system() == 'Windows':
        extlist = set(os.environ['PATHEXT'].lower().split(os.pathsep))

    for ext in extlist:
        execname = executable + ext
        for p in paths:
            f = os.path.join(p, execname)
            if os.path.isfile(f):
                return f

    return None
    raise Exception('Unable to find the required binary "%s" in PATH - maybe it was not installed properly?' % (name,))
