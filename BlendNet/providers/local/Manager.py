#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Local Manager

Description: Implementation of the Local manager
'''

import os
import hashlib
import json
from datetime import datetime

from . import LOCAL_RESOURCES
from .. import InstanceProvider
from ...ManagerAgentWorker import ManagerAgentWorker

class Manager(InstanceProvider):
    def __init__(self):
        super().__init__()
        LOCAL_RESOURCES['manager'] = {
            'id': self._cfg.instance_name,
            'name': self._cfg.instance_name,
            'ip': None,
            'internal_ip': None,
            'type': 'custom',
            'started': True,
            'stopped': False,
            'created': datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000%z'),
        }
        self._agents_dir = 'agents'
        self.agentsCustomLoad()

    def agentCustomCreate(self, agent_name, conf, save = True):
        '''Create new custom agent worker'''
        LOCAL_RESOURCES['agents'][agent_name] = {
            'id': agent_name,
            'name': agent_name,
            'ip': conf.get('ip', conf.get('address', None)),
            'internal_ip': conf.get('internal_ip', conf.get('address', None)),
            'type': 'custom',
            'started': False,
            'stopped': False,
            'created': conf.get('created', datetime.now().strftime('%Y-%m-%dT%H:%M:%S.000%z')),
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
        if save:
            save_data = {}
            save_data.update(conf)
            save_data.update(LOCAL_RESOURCES['agents'][agent_name])
            self.agentCustomSave(agent_name, save_data)
        return True

    def agentCustomRemove(self, agent_name):
        '''Remove the existing custom agent worker'''
        with self._agents_pool_lock:
            worker_index = -1
            for i, worker in enumerate(self._agents_pool):
                if worker.name() != agent_name:
                    continue
                if worker.busy():
                    return False
                worker_index = i

            if worker_index >= 0:
                self._cfg.agents_max -= 1
                self._agents_pool[worker_index].stop()
                del self._agents_pool[worker_index]
                del LOCAL_RESOURCES['agents'][agent_name]
                return True

        self.agentCustomSave(agent_name, None)

        return False

    def agentCustomSave(self, agent_name, agent_data):
        '''Save agent to disk'''
        if not agent_data:
            print('DEBUG: Removing %s agent from disk' % (agent_name,))
        else:
            print('DEBUG: Saving %s agent to disk' % (agent_name,))

        os.makedirs(self._agents_dir, 0o700, True)

        try:
            filename = 'agent-%s.json' % (hashlib.sha1(agent_name.encode('utf-8')).hexdigest(),)
            filepath = os.path.join(self._agents_dir, filename)
            if not agent_data:
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    # Could happen on Windows if file is used by some process
                    print('ERROR: Unable to remove file:', str(e))
                return
            with open(filepath, 'w') as f:
                json.dump(agent_data, f)
        except Exception as e:
            print('ERROR: Unable to save agent "%s" to disk: %s' % (agent_name, e))

    def agentsCustomLoad(self):
        '''Load agents from disk'''
        print('DEBUG: Loading agents from disk')
        if not os.path.isdir(self._agents_dir):
            return

        with os.scandir(self._agents_dir) as it:
            for entry in it:
                if not (entry.is_file() and entry.name.endswith('.json')):
                    continue
                print('DEBUG: Loading agent:', entry.name)
                json_path = os.path.join(self._agents_dir, entry.name)
                try:
                    with open(json_path, 'r') as f:
                        data = json.load(f)
                        self.agentCustomCreate(data['name'], data, save=False)
                except Exception as e:
                    print('ERROR: Unable to load agent file "%s" from disk: %s' % (json_path, e))

    def timeToTerminating(self):
        return 0
