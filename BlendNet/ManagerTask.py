#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet ManagerTask

Description: Task used by Manager to control jobs
'''

import os
import time
import threading
import statistics # Calculate good remaining time

from .TaskBase import TaskConfig, TaskState, TaskBase

class ManagerTaskConfig(TaskConfig):
    def __init__(self, parent):
        self._defs['agents_num'] = {
            'description': '''How much agents to use from the pool''',
            'type': int,
            'validation': lambda cfg, val: val <= cfg._parent._parent._cfg.agents_max,
            'min': 0,
            'default': lambda cfg: cfg._parent._parent._cfg.agents_max,
        }
        self._defs['use_compositing_nodes'] = {
            'description': '''Use compositing nodes from the project''',
            'type': bool,
            'default': True,
        }

        super().__init__(parent)

class ManagerTask(TaskBase):
    def __init__(self, manager, name, data = {}):
        super().__init__(manager, name, ManagerTaskConfig(self), data)

        with self._status_lock:
            self._status.update({
                'start_time_actual': self._status.get('start_time_actual'), # Time of the first agent task started
                'samples_per_workload': self._status.get('samples_per_workload'), # How much samples manager give to one agent
                'samples_acquired': self._status.get('samples_done', 0), # How much samples was taken to process by agents
                'workloads_taken': self._status.get('workloads_taken', 0), # How much agent tasks was taken
                'results_processing': self._status.get('results_processing'), # While results still processing task can't be completed
                'compose_filepath': self._status.get('compose_filepath'), # Composed image filepath to store the image on the Addon
            })
            self._status['result']['compose'] = self._status['result'].get('compose', None) # Blob ID of the composed image

        # Task executions by agents
        self._executions = {}
        # Info about the execution statuses used in the execution watcher
        self._execution_status = data.get('execution_status', {})

        # Task execution results and processor
        self._results_preview_lock = threading.Lock()
        self._results_preview = data.get('results_preview', {})
        self._results_render_lock = threading.Lock()
        self._results_render = data.get('results_render', {})
        self._results_watcher = None

        self._results_to_remove_lock = threading.Lock()
        self._results_to_remove = set()

        self._stop_task = False # Used to stop the task

    def snapshot(self):
        '''Returns dict with all the data about task to restore it later'''
        out = super().snapshot()
        out.update({
            'execution_status': self._execution_status.copy(),
            'results_preview': self._results_preview.copy(),
            'results_render': self._results_render.copy(),
        })
        return out

    def statusResultsProcessingSet(self, val):
        with self._status_lock:
            self._status['results_processing'] = val

    def _resultsWatcher(self):
        '''Merges multiple results from a number of agents into one result'''
        print('DEBUG: Starting ManagerTask "%s" results watcher' % self.name())

        prev_preview = set()
        prev_render = set()

        while True:
            to_merge = None
            to_compose = None

            # Preview merge in priority
            with self._results_preview_lock:
                blobs = set(self._results_preview.values())
                if blobs != prev_preview:
                    to_merge = (self.statusPreviewSet, blobs)
                    prev_preview = blobs.copy()

            # Next check to merge render results
            if not to_merge:
                with self._results_render_lock:
                    blobs = set(self._results_render.values())
                    if blobs != prev_render:
                        to_merge = (self.statusRenderSet, blobs)
                        prev_render = blobs.copy()

            # Lastly check if it's time for compositing
            with self._status_lock:
                if (not self._status['result']['compose']
                    and self._status['samples_done'] >= self._cfg.samples
                    and not self._stop_task):
                    to_compose = True

            if not to_merge:
                if not to_compose:
                    self.statusResultsProcessingSet(False)
                if not self.isRunning():
                    self.statusResultsProcessingSet(False)
                    break # If all the requests was processed and task is not running - stop
                if not to_compose:
                    time.sleep(1.0)
                    continue

            self.statusResultsProcessingSet(True)

            if to_merge:
                self._mergeWorker(to_merge)
            elif to_compose:
                self._composeWorker()

        self._results_watcher = None
        print('DEBUG: Stopped ManagerTask "%s" results watcher' % self.name())

    def _mergeWorker(self, to_merge):
        '''Merge the multiple preview or render images to one'''
        print('DEBUG: Merge started for task "%s"' % (self.name(),))
        try:
            if len(to_merge[1]) == 1:
                # Sending directly to results just one image to merge
                to_merge[0](to_merge[1].pop())
            else:
                files = dict([ ('%d.exr' % i, v) for i, v in enumerate(to_merge[1]) ])
                cfg = {
                    'images': list(files.keys()),
                    'result': 'result.exr',
                }
                with self.prepareWorkspace(files) as ws_path:
                    process = self.runBlenderScriptProcessor(ws_path, 'merge', cfg)
                    outs, errs = process.communicate()
                    if process.returncode != 0 or errs:
                        print('WARN: The merge process seems not ended well:')
                        print('WARN: Merge outputs:', outs.decode())
                        print('WARN: Merge errors:', errs.decode())
                    blob = self._parent._fc.blobStoreFile(os.path.join(ws_path, cfg['result']), True)
                    if not blob:
                        print('ERROR: Unable to store blob for merge result of "%s"' % self.name())
                        return
                    to_merge[0](blob['id'])
        except Exception as e:
            print('ERROR: Exception occurred during merging the results for task "%s": %s' % (self.name(), e))
            # Critical only on render merge
            if to_merge[0] == self.statusRenderSet:
                self.stateError({self.name(): 'Exception occurred during merging the results: %s' % (e,)})

        print('DEBUG: Merge completed for task "%s"' % (self.name(),))

        # Clean the old result blobs
        with self._results_to_remove_lock:
            if not self._results_to_remove:
                return
            print('DEBUG: Running cleaning of %s result blobs' % len(self._results_to_remove))
            for blob_id in self._results_to_remove:
                self._parent._fc.blobRemove(blob_id)
            self._results_to_remove.clear()

        print('DEBUG: Merge clean completed for task "%s"' % (self.name(),))

    def _composeWorker(self):
        '''Running blender instance to compose and export the rendered image'''
        print('DEBUG: Starting composite process for task "%s"' % (self.name(),))
        try:
            with self._status_lock:
                # Composition can use dependencies - so getting them all to the workspace
                files = self.filesGet()
                # And updating deps with the rendered image to replace the renderl layer node
                render_name = 'blendnet-' + self._status['result']['render']
                files.update({
                    render_name + '.exr': self._status['result']['render'],
                })
            cfg = {
                'project': self._cfg.project,
                'use_compositing_nodes': self._cfg.use_compositing_nodes,
                'frame': self._cfg.frame,
                'render_file_path': render_name + '.exr',
                'result_dir': render_name + '-result',
            }
            with self.prepareWorkspace(files) as ws_path:
                process = self.runBlenderScriptProcessor(ws_path, 'compose', cfg)
                outs, errs = process.communicate()
                if process.returncode != 0 or errs:
                    print('WARN: The compose process seems not ended well:')
                    print('WARN: Composite outputs:', outs.decode())
                    print('WARN: Composite errors:', errs.decode())

                # Find the compose filepath in the stdout
                compose_filepath = None
                for line in outs.decode().split('\n'):
                    line = line.strip()
                    if line.startswith('INFO: Compose filepath: '):
                        compose_filepath = line.split('INFO: Compose filepath: ', 1)[-1]
                        break

                # Checking the result_dir and set the compose if the result file is here
                for filename in os.listdir(os.path.join(ws_path, cfg['result_dir'])):
                    blob = self._parent._fc.blobStoreFile(os.path.join(ws_path, cfg['result_dir'], filename), True)
                    if not blob:
                        print('ERROR: Unable to store blob for compose result of "%s"' % self.name())
                        return
                    self.statusComposeSet(blob['id'], compose_filepath or filename)
                    break
                with self._status_lock:
                    if not self._status['result']['compose']:
                        self.stateError({self.name(): 'Result file of the compose operation not found'})

        except Exception as e:
            print('ERROR: Exception occurred during composing the result for task "%s": %s' % (self.name(), e))
            self.stateError({self.name(): 'Exception occurred during composing the result: %s' % (e,)})

        print('DEBUG: Compositing completed for task "%s"' % (self.name(),))

    def calculateWorkloadSamples(self, samples, agents):
        '''Calculating optimal number of samples per agent'''
        from math import ceil, floor
        out = min(ceil(samples/agents), 100)
        batches = floor(samples/(out*agents))
        if batches > 0:
            out += ceil(samples%(out*agents)/(batches*agents))
        return ceil(out/2) if out > 140 else out

    def acquireWorkload(self, agent):
        '''Returns map with parameters for agent to process'''
        with self._status_lock:
            if self._stop_task or not self.isRunning():
                return {} # Stopping in progress - no more workloads

            left_to_acquire = self._cfg.samples - self._status['samples_acquired']

            # "<=" just in case when more samples was calculated to prevent endless task
            if left_to_acquire <= 0:
                return {} # No work is available

            if not self._status['samples_per_workload']:
                self._status['samples_per_workload'] = self.calculateWorkloadSamples(self._cfg.samples, self._cfg.agents_num)

            workload = self.configsGet()
            # TODO: Dynamically change min samples according to the
            # time to render and loading/rendering ratio
            workload['samples'] = min(left_to_acquire, self._status['samples_per_workload'])
            self._status['samples_acquired'] += workload['samples']
            # Append to seed to make agent render unique
            workload['seed'] += self._status['workloads_taken']
            workload['task_name'] = '%s_%d' % (self.name(), self._status['workloads_taken'])

            # Put agent task into executions list
            with self._execution_lock:
                self._executions[workload['task_name']] = agent

            self._status['workloads_taken'] += 1

            return workload

    def returnAcquiredWorkload(self, samples):
        '''If agent was not able to complete the task - it could return samples back'''
        with self._status_lock:
            self._status['samples_acquired'] -= samples

    def updatePreview(self, agent_task, blob_id):
        '''Run process of merging the available previews and update the task results'''
        print('DEBUG: Updating preview for task "%s" blob id "%s"' % (agent_task, blob_id))
        old_blob_id = None
        with self._results_preview_lock:
            old_blob_id = self._results_preview.get(agent_task)
            if blob_id is None:
                if agent_task in self._results_preview:
                    self._results_preview.pop(agent_task)
            else:
                self._results_preview[agent_task] = blob_id
        if old_blob_id:
            with self._results_to_remove_lock:
                self._results_to_remove.add(old_blob_id)

    def updateRender(self, agent_task, blob_id):
        '''Run process of merging the available renders and update the task results'''
        print('DEBUG: Updating render for task "%s" blob id "%s"' % (agent_task, blob_id))
        old_blob_id = None
        with self._results_render_lock:
            old_blob_id = self._results_render.get(agent_task)
            if blob_id is None:
                if agent_task in self._results_render:
                    self._results_render.pop(agent_task)
            else:
                self._results_render[agent_task] = blob_id
        if old_blob_id:
            with self._results_to_remove_lock:
                self._results_to_remove.add(old_blob_id)

    def _executionWatcher(self):
        '''Looking for the task execution on the agents, collecting renders together'''
        print('DEBUG: Execution watcher of task "%s" is started' % self.name())

        # Will help us to combine results
        if not self._results_watcher:
            self._results_watcher = threading.Thread(target=self._resultsWatcher)
            self._results_watcher.start()

        task_end_states = {TaskState.STOPPED.name, TaskState.COMPLETED.name, TaskState.ERROR.name}
        update_messages_time = 0

        while self.isRunning():
            if self._parent.isTerminating():
                self.stop()
            with self._execution_lock:
                executions = self._executions.copy()

            for task_name, agent in executions.items():
                prev_status = self._execution_status.get(task_name, {})
                task_status = prev_status.copy()
                if prev_status.get('state') in task_end_states:
                    continue

                if agent.isActive():
                    requested_time = time.time()
                    task_status = agent.taskStatus(task_name)
                    if not task_status:
                        continue
                    task_status['_requested_time'] = requested_time # Will help with remaining calculations
                else:
                    # If it was not active before - just wait
                    if not prev_status:
                        continue
                    # If it was active - looks like the agent failed and we have to mark task as stopped
                    print('WARN: The agent become not active - invalidating its task')
                    agent.taskStop(task_name) # Try to stop the task on the agent anyway
                    task_status['state'] = TaskState.STOPPED.name

                if self._stop_task and task_status.get('state') not in task_end_states:
                    print('DEBUG: stopping Agent task %s' % task_name)
                    agent.taskStop(task_name)

                # Update task messages once per 10 sec
                if update_messages_time + 10 < time.time():
                    self.executionMessagesSet(agent.taskMessages(task_name).get(task_name), task_name)

                param = 'preview'
                if prev_status.get('result', {}).get(param) != task_status.get('result', {}).get(param):
                    print('DEBUG: task %s %s changed: %s' % (task_name, param, task_status.get('result', {}).get(param)))
                    agent.requestPreviewDownload(task_name, self.updatePreview)
                param = 'render'
                if prev_status.get('result', {}).get(param) != task_status.get('result', {}).get(param):
                    print('DEBUG: task %s %s changed: %s' % (task_name, param, task_status.get('result', {}).get(param)))
                    agent.requestRenderDownload(task_name, self.updateRender)

                param = 'state'
                if prev_status.get(param) != task_status.get(param):
                    print('DEBUG: task %s %s changed: %s' % (task_name, param, task_status.get(param)))

                    if task_status.get('state') == TaskState.RUNNING.name:
                        with self._status_lock:
                            # Set the actual start time when the first agent task reported about it
                            if not self._status['start_time_actual']:
                                self._status['start_time_actual'] = task_status.get('start_time')

                    if task_status.get('state') in task_end_states:
                        print('DEBUG: Retreive details about the task %s execution' % task_name)
                        self.executionDetailsSet(agent.taskDetails(task_name).get(task_name), task_name)
                        agent.workEnded()

                    if task_status.get('state') == TaskState.STOPPED.name:
                        print('WARN: The agent task %s was stopped' % task_name)
                        return_samples = task_status.get('samples', agent.work().get('samples'))
                        # Main task output is render - so if it's exists, we can think that some work was done
                        if task_status.get('result', {}).get('render'):
                            # If agent was able to complete some work - return the rest back to task
                            if task_status.get('samples_done'):
                                return_samples -= task_status['samples_done']
                        else:
                            # Making sure user will not see more samples than actually rendered
                            task_status['samples_done'] = 0
                            # Cleaning results of failed task
                            self.updatePreview(task_name, None)
                            self.updateRender(task_name, None)

                        if return_samples > 0:
                            print('DEBUG: Agent %s returning samples to render: %s' % (agent._name, return_samples))
                            self.returnAcquiredWorkload(return_samples)

                    if task_status.get('state') == TaskState.COMPLETED.name:
                        print('INFO: The agent task %s was completed' % task_name)

                    if task_status.get('state') == TaskState.ERROR.name:
                        print('ERROR: The agent task %s was ended with status "ERROR"' % task_name)

                self._execution_status[task_name] = task_status

            if update_messages_time + 10 < time.time():
                update_messages_time = time.time()

            # Updating the task left samples
            self.statusSamplesDoneSet(sum([ t.get('samples_done') for t in self._execution_status.values() ]))

            # Calculate the task remaining time
            time_per_sample = []
            for task, status in self._execution_status.items():
                if not (status.get('start_time') and status.get('samples')):
                    continue
                if status.get('end_time'):
                    # Simple calculation based on start and end time
                    time_per_sample.append((status['end_time'] - status['start_time']) / status['samples'])
                elif status.get('remaining') and status.get('samples_done'):
                    # Calculating time per sample based on task remaining time and left samples to render
                    prelim_render_time = status['_requested_time'] + status['remaining'] - status['start_time']
                    time_per_sample.append(prelim_render_time / status['samples'])
            if time_per_sample:
                remaining = statistics.median(time_per_sample) * (self._cfg.samples - self._status['samples_done'])
                self.statusRemainingSet(int(remaining))

            # Check if all the samples was processed and tasks completed
            with self._status_lock:
                if self._status['results_processing']:
                    # If the results are processing - let's not do anything
                    time.sleep(1.0)
                    continue

                if any([ task.get('state') == TaskState.ERROR.name for task in self._execution_status.values() ]):
                    for name, task in self._execution_status.items():
                        if not task.get('state_error_info'):
                            continue
                        print('ERROR: Agent task "%s" ended up in ERROR state' % name)
                        self.stateError({name: task.get('state_error_info')})

                elif all([ task.get('state') in task_end_states for task in self._execution_status.values() ]):
                    if self._stop_task:
                        print('INFO: Task %s is stopped' % self.name())
                        self.stateStop()
                        self._stop_task = False
                        continue
                    if self._status['result']['compose']:
                        print('INFO: Task %s is completed' % (self.name(),))
                        self.stateComplete()
                        continue
                    # >= to make sure some calculate bug will not stop the render done of the task
                    if self._status['samples_done'] >= self._cfg.samples:
                        print('INFO: Render of %s is done' % (self.name(),))
                        time.sleep(1.0)

        with self._state_lock:
            print('DEBUG: Execution watcher of task "%s" is ended with state %s' % (self.name(), self._state.name))
        with self._execution_lock:
            self._execution_watcher = None

    def statusComposeSet(self, blob_id, filepath):
        with self._status_lock:
            self._status['compose_filepath'] = filepath
            self._status['result']['compose'] = blob_id

    def _stop(self):
        self._stop_task = True

    def stateSet(self, state):
        super().stateSet(state)
        self._parent.tasksSave([self])
