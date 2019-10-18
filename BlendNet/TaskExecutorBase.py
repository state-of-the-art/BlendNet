#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet TaskExecutorBase

Description: Common for all task executors (agent/manager)
'''

import os
import signal
import time # We need to sleep the watching thread
import threading # Sync between threads needed
import json # Used in the tasks configuration
from abc import ABC

from .Config import Config
from .TaskBase import TaskConfig, TaskBase
from .FileCache import FileCache

class TaskExecutorConfig(Config):
    _defs = {
        'session_id': {
            'description': '''Session identificator''',
            'type': str,
            'default': 'test',
        },
        'bucket': {
            'description': '''Bucket name used to store things''',
            'type': str,
            'default': lambda cfg: providers.getBucketName(cfg.session_id),
        },
        'listen_host': {
            'description': '''Server listen host - ip address or name''',
            'type': str,
            'default': '',
        },
        'listen_port': {
            'description': '''Server listen port''',
            'type': int,
            'min': 1,
            'max': 65535,
            'default': 8443,
        },
        'auth_user': {
            'description': '''Server auth user name''',
            'type': str,
            'default': '',
        },
        'auth_password': {
            'description': '''Server auth password''',
            'type': str,
            'default': '',
        },
    }

class TaskExecutorBase(ABC):
    '''Class with the common task management functional'''

    def __init__(self, task_type, config):
        if not issubclass(task_type, TaskBase):
            print(task_type, TaskBase)
            raise Exception('Unable use task type %s' % task_type)
        if not isinstance(config, TaskExecutorConfig):
            raise Exception('Unable to setup with configuration %s' % type(config))

        self._enabled = True
        self._task_type = task_type

        self._cfg = config

        self._fc = FileCache('.', 'BlendNet_cache')

        self._tasks_lock = threading.Lock()
        self._tasks = {}

        self._tasks_pending_lock = threading.Lock()
        self._tasks_pending = []
        self._tasks_running_lock = threading.Lock()
        self._tasks_running = set()

        self._tasks_watcher = threading.Thread(target=self._tasksWatcher)
        self._tasks_watcher.start()

        self._old_sigint = signal.signal(signal.SIGINT, self._termSignalHook)
        self._old_sigterm = signal.signal(signal.SIGTERM, self._termSignalHook)

    def __del__(self):
        print('DEBUG: Deleting TaskExecutorBase instance')
        self._enabled = False

    def _termSignalHook(self, signum, frame):
        print('WARN: Executor received TERM %s signal...' % signum)

        self.setTerminating()

        signal.signal(signal.SIGINT, self._old_sigint or signal.SIG_DFL)
        signal.signal(signal.SIGTERM, self._old_sigterm or signal.SIG_DFL)

    def tasks(self):
        '''Returns a copy of tasks list'''
        with self._tasks_lock:
            return self._tasks.copy()

    def tasksRunning(self):
        '''Returns copy of the currently running tasks set'''
        with self._tasks_running_lock:
            return self._tasks_running.copy()

    def taskExists(self, name):
        '''Will check the existance of task'''
        with self._tasks_lock:
            return name in self._tasks

    def taskGet(self, name):
        '''Will return existing or new task object'''
        with self._tasks_lock:
            if name not in self._tasks:
                self._tasks[name] = self._task_type(self, name)
            return self._tasks[name]

    def taskToPending(self, task):
        '''Put task object into pending list'''
        with self._tasks_pending_lock:
            self._tasks_pending.append(task)
        print('DEBUG: Moving new task to pending: "%s"' % task.name())

        return True

    def _taskPendingToRunning(self):
        '''Put task object from pending into running list'''
        task = None
        with self._tasks_pending_lock:
            task = self._tasks_pending.pop(0)

        with self._tasks_running_lock:
            self._tasks_running.add(task)

        task.start()

        print('DEBUG: Moved task from pending to running: "%s"' % task.name())

        return True

    def _tasksWatcher(self):
        '''Watch on the running tasks and updating them from pending ones'''
        print('DEBUG: Starting tasks watcher')
        while self._enabled:
            with self._tasks_running_lock:
                tasks_running = self._tasks_running.copy()
                for task in tasks_running:
                    if task.isEnded(): # Remove task from the list since it's ended
                        print('DEBUG: Removing ended task "%s"' % task.name())
                        self._tasks_running.remove(task)

            if self._tasks_pending:
                if not self.tasksRunning(): # Empty running tasks
                    self._taskPendingToRunning()
                # TODO: if the current executing task is going to complete - need
                # to get the new one from pending to not spend time on preparing

            time.sleep(1.0)
        print('DEBUG: Stopped tasks watcher')

    def getLoadStatus(self):
        '''Return current load average 1, 5, 15 mins'''
        load = (None, None, None)

        if hasattr(os, 'getloadavg'): # Linux, Mac
            load = os.getloadavg()

        return load

    def getMemoryStatus(self):
        '''Return current memory status MemTotal, MemFree, MemAvailable in MB'''
        memory = {}

        if os.path.exists('/proc/meminfo'): # Linux
            with open('/proc/meminfo', 'r') as f:
                for line in f.readlines():
                    if line.startswith('Mem'):
                        memory[line.split(':')[0]] = float(line.split(' ')[-2])/1024.0

        return memory

    def getDiskStatus(self):
        '''Return disk total and available space in MB'''
        return {
            'total': self._fc.getTotalSpace()/1024/1024,
            'available': self._fc.getAvailableSpace()/1024/1024,
        }

    def blobStoreStream(self, stream, size, sha1):
        return self._fc.blobStoreStream(stream, size, sha1)

    def blobGet(self, sha1):
        return self._fc.blobGet(sha1)

    def blobGetStream(self, sha1):
        return self._fc.blobGetStream(sha1)
