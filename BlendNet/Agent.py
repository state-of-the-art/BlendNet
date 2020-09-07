#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Agent

Description: Render worker agent
'''

from .AgentTask import AgentTask
from . import providers
from .TaskExecutorBase import TaskExecutorConfig, TaskExecutorBase

class AgentConfig(TaskExecutorConfig):
    def __init__(self, parent, init = dict()):
        self._defs['listen_port']['default'] = 9443
        self._defs['instance_name'] = {
            'description': '''Agent instance name''',
            'type': str,
            'default': lambda cfg: providers.getAgentNamePrefix(cfg.session_id),
        }
        self._defs['instance_type'] = {
            'description': '''Agent instance type (size)''',
            'type': str,
            'default': lambda cfg: providers.getAgentSizeDefault(),
        }

        super().__init__(parent, init)

class Agent(TaskExecutorBase, providers.Agent):
    def __init__(self, conf):
        print('DEBUG: Creating Agent instance')
        TaskExecutorBase.__init__(self, AgentTask, AgentConfig(self, conf))

        providers.Agent.__init__(self)
