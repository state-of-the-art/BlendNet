#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Manager

Description: Render manager for agent workers
'''

import threading # Sync between threads needed

from .ManagerTask import ManagerTask
from . import providers
from .TaskExecutorBase import TaskExecutorConfig, TaskExecutorBase
from .ManagerAgentWorker import ManagerAgentWorker

class ManagerConfig(TaskExecutorConfig):
    def __init__(self, parent, init = {}):
        self._defs['instance_name'] = {
            'description': '''Manager instance name''',
            'type': str,
            'default': lambda cfg: providers.getManagerName(cfg.session_id),
        }
        self._defs['instance_type'] = {
            'description': '''Manager instance type (size)''',
            'type': str,
            'default': lambda cfg: providers.getManagerSizeDefault(),
        }
        self._defs['agents_max'] = {
            'description': '''Manager agent pool maximum''',
            'type': int,
            'min': 1,
            'max': 1000,
            'default': 3,
        }
        self._defs['agent_instance_type'] = {
            'description': '''Agent instance type (size)''',
            'type': str,
            'default': lambda cfg: providers.getAgentSizeDefault(),
        }
        self._defs['agent_use_cheap_instance'] = {
            'description': '''Use cheap VMs (preemptible, spot...) to save money''',
            'type': bool,
            'default': True,
        }
        self._defs['agent_instance_max_price'] = {
            'description': '''Maximum cheap instance price to pay for the agent''',
            'type': float,
            'min': 0.0,
            'default': None,
        }
        self._defs['agent_listen_host'] = {
            'description': '''Agent listen host - ip address or name''',
            'type': str,
            'default': '',
        }
        self._defs['agent_listen_port'] = {
            'description': '''Agent listen port''',
            'type': int,
            'min': 1,
            'max': 65535,
            'default': 9443,
        }
        self._defs['agent_auth_user'] = {
            'description': '''Agent auth user name''',
            'type': str,
            'default': '',
        }
        self._defs['agent_auth_password'] = {
            'description': '''Agent auth password''',
            'type': str,
            'default': '',
        }
        self._defs['agent_instance_prefix'] = {
            'description': '''Agent instance prefix''',
            'type': str,
            'default': lambda cfg: providers.getAgentNamePrefix(cfg.session_id),
        }
        self._defs['agent_upload_workers'] = {
            'description': '''Agent upload workers number''',
            'type': int,
            'min': 1,
            'max': 32,
            'default': 4,
        }

        super().__init__(parent, init)

class Manager(providers.Manager, TaskExecutorBase):
    def __init__(self, conf):
        print('DEBUG: Creating Manager instance')
        providers.Manager.__init__(self)
        TaskExecutorBase.__init__(self, ManagerTask, ManagerConfig(self, conf))

        self._agents_pool_lock = threading.Lock()
        self._agents_pool = []
        self._agentsPoolSetup()

        self._resources_lock = threading.Lock()
        self._resources = {}
        self._check_resources_timer_lock = threading.Lock()
        self._check_resources_timer = None
        self.resourcesGet(True)

        self.tasksLoad()

    def setTerminating(self):
        '''Overrides setTerminating function to run save tasks'''
        self.tasksSave()

        # Let's delete the agents
        with self._agents_pool_lock:
            for agent in self._agents_pool:
                print('WARN: Deleting the agent %s due to Manager termination' % agent._name)
                # We don't need to wait until delete will be completed
                thread = threading.Thread(target=providers.deleteInstance, args=(agent._id,))
                thread.daemon = True
                thread.start()

        providers.Manager.setTerminating(self)

    def __del__(self):
        TaskExecutorBase.__del__(self)
        self.tasksSave()

    def _agentsPoolSetup(self):
        '''Setup the Agents pool'''
        name_template = self._cfg.agent_instance_prefix + '%04d'
        cfg = {
            'session_id': self._cfg.session_id,
            'dist_url': self._cfg.dist_url,
            'dist_checksum': self._cfg.dist_checksum,
            'bucket': self._cfg.bucket,
            'instance_type': self._cfg.agent_instance_type,
            'use_cheap_instance': self._cfg.agent_use_cheap_instance,
            'instance_max_price': self._cfg.agent_instance_max_price,
            'listen_host': self._cfg.agent_listen_host,
            'listen_port': self._cfg.agent_listen_port,
            'auth_user': self._cfg.agent_auth_user,
            'auth_password': self._cfg.agent_auth_password,
            'instance_prefix': self._cfg.agent_instance_prefix,
            'upload_workers': self._cfg.agent_upload_workers,
        }
        with self._agents_pool_lock:
            if len(self._agents_pool) < self._cfg.agents_max:
                for i in range(len(self._agents_pool), self._cfg.agents_max):
                    self._agents_pool.append(ManagerAgentWorker(self, name_template % i, cfg))
            elif len(self._agents_pool) > self._cfg.agents_max:
                pass # TODO: it should not remove the active agents, but just mark them to remove later

    def _agentsGet(self):
        '''Get the list of agents'''
        with self._agents_pool_lock:
            return self._agents_pool.copy()

    def resourcesGet(self, quick_check = False):
        '''Run the delayed check and return the cached value'''
        with self._check_resources_timer_lock:
            if quick_check and self._check_resources_timer:
                self._check_resources_timer.cancel()
                self._check_resources_timer = None
            if self._check_resources_timer:
                with self._resources_lock:
                    return self._resources
            self._check_resources_timer = threading.Timer(0.1 if quick_check else 3, self.resourcesGetWait)
            self._check_resources_timer.start()

        with self._resources_lock:
            return self._resources

    def resourcesGetWait(self):
        '''Runs the resources get, updates the cache and return it'''
        with self._check_resources_timer_lock:
            if self._check_resources_timer:
                self._check_resources_timer.cancel()
                self._check_resources_timer = None

        res = providers.getResources(self._cfg.session_id)
        with self._resources_lock:
            self._resources = res

        return res
