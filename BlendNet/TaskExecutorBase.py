#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet TaskExecutorBase

Description: Common for all task executors (agent/manager)
'''

import os
import signal
import time # We need to sleep the watching thread
import threading # Sync between threads needed
import json # Used in the tasks save/load
import hashlib # Calculate sha1 to find a task snapshot name
from abc import ABC

from . import providers
from .Config import Config
from .TaskBase import TaskBase
from .FileCache import FileCache

class TaskExecutorConfig(Config):
    _defs = {
        'session_id': {
            'description': '''Session identificator''',
            'type': str,
            'default': 'test',
        },
        'dist_url': {
            'description': '''Blender distributive URL''',
            'type': str,
            'default': 'https://example.com/blender-test.tar.xz',
        },
        'dist_checksum': {
            'description': '''Blender distributive checksum''',
            'type': str,
            'default': '',
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
            raise Exception('Unable use task type %s' % task_type)
        if not isinstance(config, TaskExecutorConfig):
            raise Exception('Unable to setup with configuration %s' % type(config))

        self._enabled = True
        self._task_type = task_type

        self._cfg = config

        self._fc = FileCache('.', 'BlendNet_cache')

        self._tasks_lock = threading.Lock()
        self._tasks = {}

        self._tasks_dir = os.path.join('tasks', '%s-%s' % (self.__class__.__name__, self._cfg.session_id))

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

    def tasksSave(self, tasks = []):
        '''Save in-memory tasks to disk'''
        if not tasks:
            with self._tasks_lock:
                tasks = list(self._tasks.values())

        print('DEBUG: Saving %s tasks to disk' % len(tasks))

        os.makedirs(self._tasks_dir, 0o700, True)

        for task in tasks:
            try:
                filename = 'task-%s.json' % hashlib.sha1(task.name().encode('utf-8')).hexdigest()
                with open(os.path.join(self._tasks_dir, filename), 'w') as f:
                    json.dump(task.snapshot(), f)
            except Exception as e:
                print('ERROR: Unable to save task "%s" to disk: %s' % (task.name(), e))

    def tasksLoad(self):
        '''Load tasks from disk'''
        with self._tasks_lock:
            if not os.path.isdir(self._tasks_dir):
                return

            with os.scandir(self._tasks_dir) as it:
                for entry in it:
                    if not (entry.is_file() and entry.name.endswith('.json')):
                        continue
                    print('DEBUG: Loading task:', entry.name)
                    json_path = os.path.join(self._tasks_dir, entry.name)
                    try:
                        with open(json_path, 'r') as f:
                            data = json.load(f)
                            task = self._task_type(self, data['name'], data)
                            self._tasks[task.name()] = task
                            task.check()
                            if task.isPending():
                                self.taskAddToPending(task)
                    except Exception as e:
                        print('ERROR: Unable to load task file "%s" from disk: %s' % (json_path, e))

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

    def taskRemove(self, name):
        '''Removes task from the task list'''
        task = self.taskGet(name)
        if task.isRunning():
            task.stop()
        if task.isPending():
            self.taskRemoveFromPending(task)
        with self._tasks_lock:
            self._tasks.pop(name)
            # Remove the snapshot file if existing
            filename = 'task-%s.json' % hashlib.sha1(name.encode('utf-8')).hexdigest()
            filepath = os.path.join(self._tasks_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)

    def taskAddToPending(self, task):
        '''Put task object into the pending list'''
        with self._tasks_pending_lock:
            if not task.check():
                print('ERROR: Unable to set to pending not ready task %s' % task.name())
            task.statePending()
            self._tasks_pending.append(task)
        print('DEBUG: Moved task to pending: "%s"' % task.name())

        return True

    def taskRemoveFromPending(self, task):
        '''Remove task object from the pending list'''
        with self._tasks_pending_lock:
            task.stateCreated()
            self._tasks_pending.remove(task)
        print('DEBUG: Removed task from pending: "%s"' % task.name())

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
                        print('DEBUG: Removing from running list ended task "%s"' % task.name())
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
