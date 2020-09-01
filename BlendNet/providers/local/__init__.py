'''Local (your own resources with Manager & Agents)
Will use your local resources
Dependencies: none
Help: https://github.com/state-of-the-art/BlendNet/wiki/HOWTO:-Setup-provider:-Your-own-render-farm-(local)
'''
__all__ = [
    'Processor',
    'Manager',
    'Agent',
]

from ...ManagerClient import ManagerClient

# Stores the custom agents added to the Manager
CUSTOM_AGENTS = {}

def getProviderInfo():
    return {}

def getResources(session_id):
    '''Get the available resources from the Manager'''
    out = {'agents': CUSTOM_AGENTS.copy()}

    try:
        import bpy
        prefs = bpy.context.preferences.addons[__package__.split('.', 1)[0]].preferences

        # This part executed on the Addon only
        if not prefs.manager_address:
            return out

        agents = ManagerClient(prefs.manager_address, {
            'listen_port': prefs.manager_port,
            'auth_user': prefs.manager_user,
            'auth_password': prefs.manager_password_hidden,
        }).agents()

        for name, info in agents.items():
            out['agents'][name] = {
                'id': name,
                'name': name,
                'ip': info.get('ip'),
                'internal_ip': info.get('internal_ip'),
                'type': 'custom',
                'started': info.get('started'),
                'stopped': info.get('stopped'),
                'created': info.get('created'),
            }
        out['manager'] = {
            'id': prefs.manager_address,
            'name': prefs.manager_address,
            'ip': prefs.manager_address,
            'internal_ip': prefs.manager_address,
            'type': 'custom',
            'started': True,
            'stopped': False,
            'created': 'unknown',
        }
    except Exception as e:
        pass

    return out

def downloadDataFromBucket(bucket_name, path):
    if not path == 'ca.crt':
        return

    # Check if it's Addon and try to load from manager_ca_path pref
    try:
        import bpy
        prefs = bpy.context.preferences.addons[__package__.split('.', 1)[0]].preferences

        with open(prefs.manager_ca_path, 'rb') as fh:
            return fh.read()
    except:
        pass

    # Let's try to load from the current working directory (useful for Manager)
    try:
        with open('ca.crt', 'rb') as fh:
            return fh.read()
    except:
        pass

def createInstanceAgent(cfg):
    '''The agent is created already - so returning just the name'''
    return cfg['instance_name']


from .Processor import Processor
from .Manager import Manager
from .Agent import Agent
