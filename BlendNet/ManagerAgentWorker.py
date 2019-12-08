#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Manager Agent Worker

Description: Interacting with Agent and watch on the status
'''

import time # We need timestamps
import threading # Sync between threads needed
import json
from enum import Enum

from . import providers
from .AgentClient import AgentClient
from . import SimpleREST
from .Workers import Workers

class ManagerAgentState(Enum):
    UNKNOWN = 0
    DESTROYED = 1
    STOPPED = 2
    STARTED = 3
    ACTIVE = 4

class ManagerAgentWorker:
    def __init__(self, manager, name, cfg):
        print('DEBUG: Creating agent worker %s' % name)
        self._parent = manager
        self._name = name
        self._cfg = cfg

        # Generate agent certificates
        SimpleREST.generateCert(self._name, self._name)

        self._enabled = True

        self._state_lock = threading.Lock()
        self._state = ManagerAgentState.UNKNOWN
        self._state_prev = self._state
        self._state_watcher = None

        self._client = None

        self._status_lock = threading.Lock()
        self._status = {}

        self._work_lock = threading.Lock()
        self._work = {}

        self._wait_agent_lock = threading.Lock()

        self._tasks_watcher = threading.Thread(target=self._tasksWatcher)
        self._tasks_watcher.start()

        self._download_render_lock = threading.Lock()
        self._download_render = {}
        self._download_preview_lock = threading.Lock()
        self._download_preview = {}
        self._download_watcher = threading.Thread(target=self._downloadWatcher)
        self._download_watcher.start()

    def __del__(self):
        print('DEBUG: Deleting agent worker %s' % self._name)
        self._enabled = False

    def _downloadWatcher(self):
        '''Downloads stuff from the agent and store it as a blob'''
        print('DEBUG: Starting ManagerAgentWorker "%s" download watcher' % self._name)

        def getDownloadFrom(download_map, result):
            out = None
            for task_name in download_map:
                out = (task_name, result, download_map[task_name])
                break
            if out:
                download_map.pop(out[0])
            return out

        while self._enabled:
            to_download = None
            # Render download in priority - it's the task result
            with self._download_render_lock:
                to_download = getDownloadFrom(self._download_render, 'render')

            if not to_download:
                with self._download_preview_lock:
                    to_download = getDownloadFrom(self._download_preview, 'preview')

            if not to_download:
                time.sleep(1.0)
                continue

            self._waitAgent()
            ret = self._client.taskResultDownloadStream(to_download[0], to_download[1], self._parent._fc.blobStoreStream)
            if not ret:
                print('ERROR: Requested download of %s was not retreived from the agent task "%s"' % (to_download[1], to_download[0]))
            else:
                to_download[2](to_download[0], ret['id'])

        print('DEBUG: Stopped ManagerAgentWorker download watcher')

    def _tasksWatcher(self):
        '''Watch on the manager's running tasks if the current task is completed'''
        current_task = None
        last_time_had_task = None

        print('DEBUG: Starting ManagerAgentWorker "%s" tasks watcher' % self._name)
        while self._enabled:
            # Make sure the agent is ok - it could be preempted any second
            # and we can't get new tasks if it's going to shutdown
            if self.status().get('terminating'):
                print('DEBUG: The agent %s is going to be stopped soon' % self._name)
                time.sleep(5.0)
                continue

            if self.busy():
                if not current_task.isRunning():
                    print('WARN: Stopping the current task "%s" - manager task is not running anymore' % current_task.name())
                    self.taskStop(self._work['task_name'])
                    self.workEnded()
                time.sleep(1.0)
                last_time_had_task = time.time()
                continue

            # Try to continue the current task
            if current_task:
                with self._work_lock:
                    self._work = current_task.acquireWorkload(self)

            if not self._work:
                # Going through tasks from old to new to get some work
                tasks = self._parent.tasksRunning()
                for task in tasks:
                    with self._work_lock:
                        self._work = task.acquireWorkload(self)
                    if self._work:
                        current_task = task
                        break

            if self._work:
                last_time_had_task = time.time()
                print('DEBUG: New workload for "%s": %s' % (self._name, self._work))
                # Upload deps anyway - who knows, maybe agent was destroyed
                # It will take not long time if files are already uploaded
                if not self.uploadFiles(self._work['task_name'], current_task.filesGet()):
                    current_task.stateError('Unable to upload the required files')
                    self.workEnded()
                    continue
                self.sendWorkload(self._work['task_name'], self._work)
                self.runWorkload(self._work['task_name'])
            elif last_time_had_task and time.time() > last_time_had_task + 300:
                print('WARN: Stopping the agent "%s" - there was no tasks for 5 mins' % self._name)
                providers.stopInstance(self._name)
                last_time_had_task = None

            time.sleep(1.0)
        print('DEBUG: Stopped ManagerAgentWorker tasks watcher')

    def _activateStateWatcher(self):
        '''Will watch the agent state until it will be lower than STARTED'''
        with self._state_lock:
            if not self._state_watcher:
                self._state_watcher = threading.Thread(target=self._stateWatcher)
                self._state_watcher.start()

    def _setState(self, state):
        '''Set the current state and saves previous one'''
        if state == self.state():
            return
        with self._state_lock:
            self._state_prev = self._state
            self._state = state

    def state(self):
        with self._state_lock:
            return self._state

    def isActive(self):
        return self.state() == ManagerAgentState.ACTIVE

    def _stateWatcher(self):
        '''Watch on the agent state'''
        print('DEBUG: Starting agent state watcher %s' % self._name)
        agent = self._parent.resourcesGet().get('agents', {}).get(self._name, {})
        while self._enabled:
            # Destroy agent if it's type is wrong
            if agent and agent.get('type') != self._cfg['instance_type']:
                print('WARN: Agent %s is type "%s" but should be "%s" - terminating' % (self._name, agent.get('type'), self._cfg['instance_type']))
                providers.deleteInstance(self._name)

            # STARTED/ACTIVE - check agent status
            if self.state() in (ManagerAgentState.STARTED, ManagerAgentState.ACTIVE):
                status = self._client.status()
                with self._status_lock:
                    self._status = status or {}
                self._setState(ManagerAgentState.ACTIVE if status else ManagerAgentState.STARTED)
                if status:
                    # No need to check the resources
                    time.sleep(1.0)
                    continue

            agent = self._parent.resourcesGet().get('agents', {}).get(self._name, {})
            if not agent:
                self._setState(ManagerAgentState.DESTROYED)
                self._client = None
                with self._status_lock:
                    self._status = {}
            elif agent.get('stopped'):
                self._setState(ManagerAgentState.STOPPED)
                with self._status_lock:
                    self._status = {}
            elif agent.get('started') and self.state() != ManagerAgentState.ACTIVE:
                if not self._client:
                    self._client = AgentClient(agent['internal_ip'], self._cfg)
                self._setState(ManagerAgentState.STARTED)

            # STARTED/ACTIVE -> STOPPED/DESTROYED - stop watcher
            if self._state_prev in (ManagerAgentState.STARTED, ManagerAgentState.ACTIVE) \
                    and self.state() in (ManagerAgentState.STOPPED, ManagerAgentState.DESTROYED):
                break

            time.sleep(5.0)

        print('DEBUG: Stopped agent watcher %s' % self._name)
        self._state_watcher = None

    def _startAgent(self):
        '''Create and start the agent if it's needed'''
        if self.state() in (ManagerAgentState.STOPPED, ManagerAgentState.DESTROYED):
            # Agent will need config files almost right after the start
            providers.uploadFileToBucket('%s.key' % self._name, self._cfg['bucket'], 'work_%s/server.key' % self._name)
            providers.uploadFileToBucket('%s.crt' % self._name, self._cfg['bucket'], 'work_%s/server.crt' % self._name)
            providers.uploadDataToBucket(json.dumps(self._cfg).encode('utf-8'), self._cfg['bucket'], 'work_%s/agent.json' % self._name)

        if self.state() == ManagerAgentState.STOPPED:
            print('DEBUG: Starting the existing agent instance "%s"' % self._name)
            self._setState(ManagerAgentState.UNKNOWN)
            providers.startInstance(self._name)
        elif self.state() == ManagerAgentState.DESTROYED:
            print('DEBUG: Creating a new agent instance "%s"' % self._name)
            itype = self._cfg['instance_type']
            self._setState(ManagerAgentState.UNKNOWN)
            providers.createInstanceAgent(itype, self._cfg['session_id'], self._name)

    def _waitAgent(self):
        '''Will wait for agent availability'''
        with self._wait_agent_lock:
            while self._enabled:
                if self.state() == ManagerAgentState.ACTIVE:
                    return True

                self._activateStateWatcher()
                self._startAgent()

                time.sleep(5.0)

    def uploadFiles(self, task_name, files_map):
        '''Uploads the task files to the Agent'''
        print('DEBUG: Uploading %d files to Agent "%s" task "%s"' % (len(files_map), self._name, task_name))
        self._waitAgent()

        workers = Workers(
            'Uploading to Agent "%s" task "%s"' % (self._name, task_name),
            self._cfg['upload_workers'],
            self._uploadFilesWorker,
        )

        workers.addSet(set( (task_name, path, sha1) for path, sha1 in files_map.items() ))
        if workers.wait():
            print('DEBUG: Uploading files to Agent "%s" task "%s" completed' % (self._name, task_name))
            return True

        print('ERROR: Unable to upload task "%s" files: %s' % (task_name, workers.tasksFailed()))
        return False

    def _uploadFilesWorker(self, task, rel_path, sha1):
        '''Gets item and uploads using client'''
        while self._enabled:
            size = self._parent.blobGet(sha1).get('size')
            with self._parent.blobGetStream(sha1) as stream:
                ret = self._client.taskFileStreamPut(task, rel_path, stream, size, sha1)
                if ret:
                    break
                print('WARN: Uploading of "%s" to task "%s" failed, repeating...' % (rel_path, task))
                time.sleep(1.0)

        print('DEBUG: Uploading of "%s" to task "%s" completed' % (rel_path, task))

    def sendWorkload(self, task_name, workload):
        '''Sending task configuration to the Agent'''
        print('DEBUG: Sending workload to Agent "%s" task "%s"' % (self._name, task_name))
        self._waitAgent()
        self._client.taskConfigPut(task_name, workload)

    def runWorkload(self, task_name):
        print('DEBUG: Run task "%s" on Agent "%s"' % (self._name, task_name))
        self._waitAgent()
        self._client.taskRun(task_name)

    def status(self):
        '''Returns the current agent status'''
        with self._status_lock:
            return self._status.copy()

    def busy(self):
        '''Returns True if worker have some work to do'''
        with self._work_lock:
            return bool(self._work)

    def work(self):
        '''Returns current workload'''
        with self._work_lock:
            return self._work.copy()

    def workEnded(self):
        '''ManagerTask marking agent as available again'''
        with self._work_lock:
            self._work = {}

    def taskStatus(self, task_name):
        '''Requesting the task status from agent'''
        if self._client:
            return self._client.taskStatus(task_name)

    def taskMessages(self, task_name):
        '''Requesting the task messages from agent'''
        if self._client:
            return self._client.taskMessages(task_name)
        return {}

    def taskDetails(self, task_name):
        '''Requesting the task details from agent'''
        if self._client:
            return self._client.taskDetails(task_name)
        return {}

    def taskStop(self, task_name):
        '''Stopping the task activity on the agent'''
        if self._client:
            return self._client.taskStop(task_name)

    def requestPreviewDownload(self, task_name, callback):
        '''Put new request to download a current preview image from the agent task'''
        with self._download_preview_lock:
            self._download_preview[task_name] = callback

    def requestRenderDownload(self, task_name, callback):
        '''Put new request to download a current render image from the agent task'''
        with self._download_render_lock:
            self._download_render[task_name] = callback
