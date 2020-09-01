#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Local Manager

Description: Implementation of the Local manager
'''

from datetime import datetime

from . import CUSTOM_AGENTS
from .. import InstanceProvider
from ...ManagerAgentWorker import ManagerAgentWorker

class Manager(InstanceProvider):
    def agentCustomCreate(self, agent_name, conf):
        '''Create new custom agent worker'''
        CUSTOM_AGENTS[agent_name] = {
            'id': agent_name,
            'name': agent_name,
            'ip': conf.get('address', None),
            'internal_ip': conf.get('address', None),
            'type': 'custom',
            'started': True,
            'stopped': False,
            'created': datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000%z'),
        }
        cfg = {
            'listen_port': conf.get('port', None),
            'auth_user': conf.get('auth_user', self._cfg.agent_auth_user),
            'auth_password': conf.get('auth_password', self._cfg.agent_auth_password),
            'upload_workers': conf.get('upload_workers', self._cfg.agent_upload_workers),
        }
        with self._agents_pool_lock:
            self._cfg.agents_max += 1
            self._agents_pool.append(ManagerAgentWorker(self, agent_name, cfg))
        return True

    def agentCustomRemove(self, agent_name):
        '''Remove the existing custom agent worker'''
        with self._agents_pool_lock:
            worker_id = -1
            for i, worker in enumerate(self._agents_pool):
                if worker.name() != agent_name:
                    continue
                if worker.busy():
                    return False
                worker_id = i

            if worker_id >= 0:
                self._cfg.agents_max -= 1
                self._agents_pool[worker_id].stop()
                del self._agents_pool[worker_id]
                del CUSTOM_AGENTS[agent_name]
                return True

        return False

    def agentCustomList(self):
        '''Returns the list of custom agents and their info'''
        return CUSTOM_AGENTS.copy()

    def timeToTerminating(self):
        return 0
