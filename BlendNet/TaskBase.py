#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet TaskBase

Description: Base functionality for any task
'''

import os, sys
import json
import time
import threading
import subprocess
from enum import Enum
from random import randrange
from abc import ABC, abstractmethod

from .Config import Config

class TaskConfig(Config):
    _defs = {
        'project': {
            'description': '''Set the project file will be used to render''',
            'type': str,
            'validation': lambda cfg, val: cfg._parent.fileGet(val),
        },
        'samples': {
            'description': '''How much samples to process for the task''',
            'type': int,
            'min': 1,
            'default': 100,
        },
        'seed': {
            'description': '''Seed to use during render (or random will be used)''',
            'type': int,
            'min': 0,
            'max': 2147483647,
            'value': lambda cfg: randrange(0, 2147483647),
        },
        'frame': {
            'description': '''Set the frame to render (or current one will be used)''',
            'type': int,
            'min': 0,
        },
    }

class TaskState(Enum):
    CREATED = 0   # Just created and not started
    STOPPED = 1   # Is stopped and waiting to start - could be partially executed
    PENDING = 2   # When it's triggered to execute, but there is not enough available executors
    RUNNING = 3   # Task is used by at least one executor
    COMPLETED = 4 # No more actions is required and results could be collected
    ERROR = 5     # Error happened during task execution or validation

class TaskBase(ABC):
    '''Class with the common task functional'''

    def __init__(self, parent, name, config, data = dict()):
        print('DEBUG: Creating new task %s' % name)
        if not isinstance(config, TaskConfig):
            raise Exception('Unable to set task with configuration %s' % type(config))

        self._parent = parent
        self._cfg = config

        self._name = name
        self._create_time = data.get('create_time', int(time.time()))
        self._start_time = data.get('start_time')
        self._end_time = data.get('end_time')

        self._status_lock = threading.Lock()
        self._status = data.get('status', {
            'samples_done': 0, # How much samples is processed
            'remaining': None, # Estimated time to complete the task
            'result': {
                'preview': None, # Blob ID of the preview exr image
                'render': None, # Blob ID of the render image
            },
        })

        # Task can't be in RUNNING state during creation
        self._state_lock = threading.Lock()
        state_name = data.get('state', TaskState.CREATED.name)
        self._state = TaskState[state_name] if state_name != TaskState.RUNNING.name else TaskState.STOPPED
        self._state_error_info = data.get('state_error_info', [])

        self._execution_lock = threading.Lock()
        self._execution_watcher = None

        self._execution_details_lock = threading.Lock()
        self._execution_details = data.get('execution_details', {})
        self._execution_messages_lock = threading.Lock()
        self._execution_messages = data.get('execution_messages', {})

        self._files_lock = threading.Lock()
        self._files = data.get('files', {})

        # Configuring here because configs using some internal task structures
        if 'config' in data:
            self._cfg.configsSet(data['config'])

    def __del__(self):
        print('DEBUG: Deleting task %s' % self.name())
        self.stop()

    def name(self):
        return self._name

    def snapshot(self):
        '''Returns dict with all the data about task to restore it later'''
        out = {
            'config': self._cfg.configsGet(),
            'status': self._status.copy(),
            'name': self._name,
            'create_time': self._create_time,
            'start_time': self._start_time,
            'end_time': self._end_time,
            'state': self._state.name,
            'state_error_info': self._state_error_info,
            'execution_details': self._execution_details.copy(),
            'execution_messages': self._execution_messages.copy(),
            'files': self._files.copy(),
        }
        return out

    def info(self):
        '''Returns info about the task'''
        out = {
            'name': self.name(),
            'create_time': self._create_time,
            'start_time': self._start_time,
            'end_time': self._end_time,
            'state': self._state.name,
            'done': self._status['samples_done'] / self._cfg.samples,
        }
        if self._state_error_info:
            out['state_error_info'] = self._state_error_info
        return out

    def status(self):
        '''Returns the task current status information'''
        with self._status_lock:
            out = self.info()
            out.update({
                'project': self._cfg.project,
                'samples': self._cfg.samples,
                'seed': self._cfg.seed,
                'frame': self._cfg.frame,
            })
            out.update(self._status)
            return out

    def statusRemainingSet(self, remaining):
        with self._status_lock:
            self._status['remaining'] = remaining

    def statusSamplesDoneSet(self, samples):
        with self._status_lock:
            self._status['samples_done'] = samples

    def statusPreviewSet(self, blob_id):
        with self._status_lock:
            self._status['result']['preview'] = blob_id

    def statusRenderSet(self, blob_id):
        with self._status_lock:
            self._status['result']['render'] = blob_id

    def canBeChanged(self):
        '''Returns True or False'''
        with self._state_lock:
            return self._state == TaskState.CREATED

    def isPending(self):
        '''Returns True or False'''
        with self._state_lock:
            return self._state == TaskState.PENDING

    def isRunning(self):
        '''Returns True or False'''
        with self._state_lock:
            return self._state == TaskState.RUNNING

    def isCompleted(self):
        '''Returns True or False'''
        with self._state_lock:
            return self._state == TaskState.COMPLETED

    def isError(self):
        '''Returns True or False'''
        with self._state_lock:
            return self._state == TaskState.ERROR

    def isStopped(self):
        '''Returns True or False'''
        with self._state_lock:
            return self._state == TaskState.STOPPED

    def isEnded(self):
        '''If task was executed, but ended it's execution'''
        with self._state_lock:
            return self._state in (TaskState.COMPLETED, TaskState.STOPPED)

    def stateCreated(self):
        with self._state_lock:
            if self._state == TaskState.PENDING:
                self.stateSet(TaskState.CREATED)

    def statePending(self):
        with self._state_lock:
            if self._state in (TaskState.CREATED, TaskState.STOPPED):
                self.stateSet(TaskState.PENDING)

    def stateStop(self):
        with self._state_lock:
            if self._state == TaskState.RUNNING:
                self._end_time = int(time.time())
                self.stateSet(TaskState.STOPPED)

    def stateComplete(self):
        with self._state_lock:
            if self._state == TaskState.RUNNING:
                self._end_time = int(time.time())
                self.stateSet(TaskState.COMPLETED)

    def stateError(self, info):
        with self._state_lock:
            self._state_error_info.append(info)
            self.stateSet(TaskState.ERROR)

    def stateSet(self, state):
        '''Unify state set of the task'''
        self._state = state

    def fileAdd(self, path, file_id):
        '''Add file to the files map'''
        if path.startswith('/') or '../' in path:
            return print('WARN: Unable to use path with absolute path or contains parent dir symlink')

        if not self.canBeChanged():
            return print('WARN: Unable to change the task once started')

        with self._files_lock:
            self._files.update({path: file_id})

        return True

    def fileGet(self, path):
        '''Get file blob id'''
        with self._files_lock:
            return self._files.get(path)

    def filesGet(self):
        '''Get files map copy'''
        with self._files_lock:
            return self._files.copy()

    def run(self):
        '''Trigger the task to execute'''
        with self._state_lock:
            if self._state not in (TaskState.CREATED, TaskState.STOPPED):
                print('WARN: Unable to run already started task')
                return True

            print('DEBUG: Starting task %s' % self.name())

        return self._parent.taskAddToPending(self)

    def start(self):
        '''Starting task execution'''
        with self._execution_lock:
            with self._state_lock:
                self._state = TaskState.RUNNING
            if not self._execution_watcher:
                self._start_time = int(time.time())
                self._execution_watcher = threading.Thread(target=self._executionWatcher)
                self._execution_watcher.start()
        print('INFO: Task %s started execution' % self.name())

    @abstractmethod
    def _executionWatcher(self):
        '''Process watching on the execution'''

    def stop(self):
        '''Stop the task execution and collect results to maybe continue the task later'''
        if self.isPending():
            self._parent.taskRemoveFromPending(self)
        if self.isRunning():
            self._stop()

    @abstractmethod
    def _stop(self):
        '''Activate the stop process and return'''

    def executionDetailsGet(self):
        '''Variety of details about the execution'''
        with self._execution_details_lock:
            return self._execution_details.copy()

    def executionDetailsAdd(self, details, task = None):
        '''Adds a new details to the list'''
        if not isinstance(details, list):
            details = [details]
        if not isinstance(task, str):
            task = self.name()
        self.executionDetailsSet(self._execution_details.get(task, []) + details, task)

    def executionDetailsSet(self, details, task = None):
        '''Set execution details'''
        with self._execution_details_lock:
            if task:
                self._execution_details[task] = details
            else:
                self._execution_details = details

    def executionMessagesGet(self):
        '''Variety of details about the execution'''
        with self._execution_messages_lock:
            return self._execution_messages.copy()

    def executionMessagesAdd(self, messages, task = None):
        '''Adds new execution messages to the list'''
        if not isinstance(messages, list):
            messages = [messages]
        if not isinstance(task, str):
            task = self.name()
        self.executionMessagesSet(self._execution_messages.get(task, []) + messages, task)

    def executionMessagesSet(self, messages, task = None):
        '''Set execution messages'''
        with self._execution_messages_lock:
            if task:
                self._execution_messages[task] = messages
            else:
                self._execution_messages = messages

    def configsSet(self, configs):
        '''Set the defined configurations and skip not defined'''
        if not self.canBeChanged():
            return print('WARN: Unable to change the task once started')

        self._cfg.configsSet(configs)
        return True

    def configsGet(self):
        '''Get all the set configs'''
        return self._cfg.configsGet()

    def check(self):
        '''Check the task integrity'''
        errors = []
        with self._files_lock:
            for path, sha1 in self._files.items():
                if not self._parent._fc.blobGet(sha1):
                    errors.append('Unable to find required file "%s" with id "%s" in file cache' % (path, sha1))
        if errors:
            self.stateError(errors)
        return True

    def prepareWorkspace(self, files_map = None):
        '''Preparing workspace to process files'''
        ws_dir = self._parent._fc.workspaceCreate(self.name(), files_map or self.filesGet())
        if not ws_dir:
            raise Exception('ERROR: Unable to prepare workspace to execute task')

        return ws_dir

    def runBlenderScriptProcessor(self, workspace_path, script_suffix, cfg = None):
        '''Running blender in workspace with providing a script path'''

        config_name = 'config-%s.json' % script_suffix
        with open(os.path.join(workspace_path, config_name), 'w') as f:
            json.dump(cfg or self.configsGet(), f)

        script_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'script-%s.py' % script_suffix)
        return subprocess.Popen(
            [sys.executable, '-b', '-noaudio', '-y', '-P', script_path, '--', config_name],
            cwd = workspace_path,
            stdin = subprocess.PIPE, # To send commands to the process
            stdout = subprocess.PIPE, # To get the current status of executing
            stderr = subprocess.PIPE, # To get messages from the running python script
        )
