from .InstanceProvider import InstanceProvider

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
selected_provider = 'local'

def loadProviders():
    '''Go through the folders in the module dir and loads the providers'''
    with os.scandir(os.path.dirname(__file__)) as it:
        for entry in it:
            if not entry.is_dir() or entry.name.startswith('__') or entry.name in modules:
                continue
            print('INFO: Found provider "%s"' % entry.name)

            try:
                modules[entry.name] = importlib.import_module('.'+entry.name, __package__)
            except Exception as e:
                print('WARN: Unable to load "%s" provider due to init error: %s' % (entry.name, e))
                #traceback.print_exc()
                modules[entry.name] = 'ERROR: Unable to load provider: %s' % (e,)

def selectProvider(provider, settings = dict()):
    '''Sets the current provider identifier'''
    if provider not in modules:
        raise Exception('Unable to set unknown provider "%s"' % provider)

    if isinstance(modules[provider], str):
        print('WARN: Unable to select "%s" provider due to loading error: %s' % (provider, modules[provider]))
        return

    check = modules[provider].checkDependencies(settings)
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

def initProvider(settings):
    '''Init provider with settings'''
    return _execProviderFunc('initProvider', None, settings)

def getProviderMessages(provider):
    '''Returns messages happening in the provider module'''
    return modules_messages.get(provider, [])

def getProvidersDoc():
    '''Return map with {ident: (name, desc), ...} of the providers'''
    out = {}
    for ident, module in modules.items():
        if isinstance(module, str):
            out[ident] = (ident + ' - ERROR: unable to initialize', module)
            continue
        name, desc = module.__doc__.split('\n', 1)
        out[ident] = (name.strip(), desc.strip())

    return out

def getProvidersSettings(provider = None):
    '''Get the available providers settings'''
    out = dict()
    for ident, module in modules.items():
        if isinstance(module, str):
            continue
        if provider and ident == provider:
            return module.getSettings()
        out[ident] = module.getSettings()
    return out

def getProviderSettings():
    '''Get the current provider settings'''
    return _execProviderFunc('getSettings')

def getSelectedProvider():
    '''Return a list with provider identifiers if their deps are ok'''
    return selected_provider

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

def uploadFileToStorage(path, storage_url, dest_path = None):
    '''Uploads file to the network storage'''
    return _execProviderFunc('uploadFileToStorage', None, path, storage_url, dest_path)

def uploadRecursiveToStorage(path, storage_url, dest_path = None, include = None, exclude = None):
    '''Recursively upload files to the storage'''
    return _execProviderFunc('uploadRecursiveToStorage', None, path, storage_url, dest_path, include, exclude)

def uploadDataToStorage(data, storage_url, dest_path = None):
    '''Uploads data to the network storage'''
    return _execProviderFunc('uploadDataToStorage', None, data, storage_url, dest_path)

def getResources(session_id):
    '''Returns map of allocated resources - manager and agents'''
    # Agents are stored with the name keys
    return _execProviderFunc('getResources', {'agents':{}}, session_id)

def getNodeLog(instance_id):
    '''Returns string with the node serial output log'''
    return _execProviderFunc('getNodeLog', 'NOT IMPLEMENTED', instance_id)

def getStorageUrl(session_id):
    return _execProviderFunc('getStorageUrl', None, session_id)

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

def downloadDataFromStorage(storage_url, path = None):
    return _execProviderFunc('downloadDataFromStorage', None, storage_url, path)

def createFirewall(target_tag, port):
    return _execProviderFunc('createFirewall', None, target_tag, port)

def setupStorage(storage_url, cfg):
    '''Creating the storage and uploads the blendnet and configs into'''
    print('INFO: Uploading BlendNet logic to the storage')

    _execProviderFunc('createStorage', None, storage_url)

    # Upload BlendNet logic from the addon
    dirpath = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    uploadRecursiveToStorage(dirpath, storage_url, 'blendnet', '*.py')
    
    import json
    uploadDataToStorage(json.dumps(cfg).encode('utf-8'), storage_url, 'work_manager/manager.json')

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
