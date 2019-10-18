'''Local
Will use your local resources only
Dependencies: none
'''
__all__ = [
    'Manager',
    'Agent',
]

def getProviderInfo():
    return {}

from .Manager import Manager
from .Agent import Agent
