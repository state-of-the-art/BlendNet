from .AgentClient import AgentClient
from .ManagerClient import ManagerClient

from . import addon

import os

def getBlInfo():
    '''Gets part of addon init and returns the version'''
    out = {}
    with open(os.path.join(os.path.dirname(__file__), '..', '__init__.py'), 'r') as f:
        info = []
        for line in f:
            if not (info or line.startswith('bl_info = {')):
                continue

            info.append(line.rstrip())

            if line.startswith('}'):
                break
        exec(''.join(info), out)
    return out['bl_info']

def getVersion():
    '''Returns the version of BlendNet'''
    bl_info = getBlInfo()
    out = '%d.%d.%d' % bl_info['version']
    if bl_info.get('warning'):
        out += '-{}'.format(bl_info.get('warning').split()[0])
    return out
