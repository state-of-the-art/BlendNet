#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Local Manager

Description: Implementation of the Local manager
'''

from datetime import datetime

from . import LOCAL_RESOURCES
from .. import InstanceProvider
from ...ManagerAgentWorker import ManagerAgentWorker

class Manager(InstanceProvider):
    def __init__(self, conf):
        super().__init__(conf)
        LOCAL_RESOURCES['manager'] = {
            'id': conf.get('name', 'None'),
            'name': conf.get('name', 'None'),
            'ip': conf.get('ip'),
            'internal_ip': conf.get('internal_ip', conf.get('ip')),
            'type': 'custom',
            'started': True,
            'stopped': False,
            'created': datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000%z'),
        }

    def agentCustomCreate(self, agent_name, conf):
        '''Create new custom agent worker'''
        LOCAL_RESOURCES['agents'][agent_name] = {
            'id': agent_name,
            'name': agent_name,
            'ip': conf.get('address', None),
            'internal_ip': conf.get('address', None),
            'type': 'custom',
            'started': False,
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
            worker = ManagerAgentWorker(self, agent_name, cfg)
            self._agents_pool.append(worker)
            # Run the Agent on worker
            worker.runAgent()
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
                del LOCAL_RESOURCES['agents'][agent_name]
                return True

        return False

    def timeToTerminating(self):
        return 0
