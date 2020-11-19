#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet AgentTask

Description: Task used by Agent to control jobs
'''

import os
import time
import signal
import threading # To run stderr reading thread
from subprocess import TimeoutExpired

from .TaskBase import TaskConfig, TaskBase

class AgentTaskConfig(TaskConfig):
    pass

class AgentTask(TaskBase):
    def __init__(self, agent, name):
        super().__init__(agent, name, AgentTaskConfig(self))

        with self._status_lock:
            self._status['result']['statistics'] = None
            self._status['result']['prepare_time'] = None
            self._status['result']['render_time'] = None

        self._stop_task = False

        # Special thread to watch for stderr stream messages
        self._execution_stderr_watcher = None
        print('DEBUG: Created Agent task', name)

    def statusStatisticsSet(self, statistics):
        with self._status_lock:
            self._status['result']['statistics'] = statistics

    def statusPrepareTimeSet(self, time_sec):
        with self._status_lock:
            self._status['result']['prepare_time'] = time_sec

    def statusRenderTimeSet(self, time_sec):
        with self._status_lock:
            self._status['result']['render_time'] = time_sec

    def _executionWatcher(self):
        '''Preparing workspace, running execution and watch on it'''
        print('DEBUG: Execution watcher of task "%s" is started' % self.name())

        try:
            files_map = self.filesGet()
            print('DEBUG: Files to use in workspace:')
            for path in sorted(files_map):
                print('DEBUG:  ', files_map[path], path)
            with self.prepareWorkspace(files_map) as ws_path:
                process = self.runBlenderScriptProcessor(ws_path, 'render', self.configsGet(), blendfile=self._cfg.project)
                self._execution_stderr_watcher = threading.Thread(target=self._executionStderrWatcher, args=(process, ws_path))
                self._execution_stderr_watcher.start()
                self._watchBlenderScriptProcessor(process, ws_path)
            print('DEBUG: Destroyed the workspace')
        except Exception as e:
            print('ERROR: Exception occurred during task "%s" execution: %s' % (self.name(), e))
        finally:
            self._parent._fc.workspaceClean(self.name())

        print('INFO: Execution of the task "%s" is ended' % self.name())
        self.stateStop()

        with self._execution_lock:
            self._execution_watcher = None

        with self._state_lock:
            print('DEBUG: Execution watcher of task "%s" is stopped with state %s' % (self.name(), self._state.name))

    def _executionStderrWatcher(self, process, workspace):
        '''Watching stderr to get response from the process script'''
        print('INFO: Starting process stderr read')

        for line in iter(process.stderr.readline, b''):
            l = ''
            try:
                l = line.decode('utf-8').rstrip()
            except LookupError:
                # UTF-8 not worked, so probably it's latin1
                l = line.decode('iso-8859-1').rstrip()
            print(">err>> %s" % l)
            self.executionMessagesAdd(l.strip())

            # Saving the results
            if l.startswith('INFO: Command "savePreview" completed'):
                blob = self._parent._fc.blobStoreFile(os.path.join(workspace, 'preview.exr'))
                self.statusPreviewSet(blob['id'] if blob else None)
            elif l.startswith('INFO: Command "saveRender" completed'):
                file_path = os.path.join(workspace, 'render.exr')
                blob = self._parent._fc.blobStoreFile(file_path, True)
                if blob:
                    print('DEBUG: got the render blob', blob['id'], blob['size'])
                self.statusRenderSet(blob['id'] if blob else None)
        self._execution_stderr_watcher = None

    def _watchBlenderScriptProcessor(self, process, workspace):
        '''Watching blender stdout and sending commands to the process'''
        print('INFO: Starting process stdout read')

        prepare_time = None

        # Task is properly finished
        finished = False
        # Task was interrupted
        interrupted = False
        # Used to capture previews periodically
        sample_preview_save_time = 0
        # Used to contain the current rendering sample
        curr_sample = 0
        for line in iter(process.stdout.readline, b''):
            l = ''
            try:
                l = line.decode('utf-8').rstrip()
            except LookupError:
                # UTF-8 not worked, so probably it's latin1
                l = line.decode('iso-8859-1').rstrip()
            print(">std>> %s" % l)

            if l.startswith('Fra:'):
                status = l.split(' | ')
                frame = None
                time_sec = None
                mem_total = None
                mem_total_peak = None
                mem_render = None
                mem_render_peak = None
                rem = None

                rest_status = None
                scene_info = None
                operation = None
                for i, s in enumerate(status):
                    if s.startswith('Fra:'): # Fra:251 Mem:1527.53M (0.00M, Peak 1538.54M)
                        d = s.split(' ')
                        frame = int(d[0].split(':')[1])
                        mem_total = float(d[1].split(':')[1][:-1])
                        mem_total_peak = float(d[-1][:-2])
                    if s.startswith('Time:'): # Time:00:09.63
                        time_data = s.split(':')[1:]
                        time_sec = float(time_data.pop(-1))
                        res = [60, 60*60, 24*60*60]
                        time_sec += sum([ int(time_data.pop(-1))*res[i] for i in range(len(time_data)) ])
                    if s.startswith('Remaining:'): # Remaining:00:17.49
                        rem_data = s.split(':')[1:]
                        rem = float(rem_data.pop(-1))
                        res = [60, 60*60, 24*60*60]
                        rem += sum([ int(rem_data.pop(-1))*res[i] for i in range(len(rem_data)) ])
                        self.statusRemainingSet(rem)
                    if s.startswith('Mem:'): # Mem:639.60M, Peak:639.60M
                        d = s.split(' ')
                        mem_render = float(d[0].split(':')[1][:-2])
                        mem_render_peak = float(d[1].split(':')[1][:-1])
                        rest_status = i+1
                        break
                if rest_status: # Scene, RenderLayer | Synchronizing object | Ship_Floor
                                # Scene, RenderLayer | Path Tracing Sample 1/10
                    scene_info = status[rest_status]
                    operation = ' | '.join(status[rest_status+1:])
                    if 'Path Tracing Sample' in operation:
                        operation, curr_sample = operation.split(' Sample ')
                        curr_sample = int(curr_sample.split('/')[0])
                        self.statusSamplesDoneSet(curr_sample-1)
                self.executionDetailsAdd({
                    'time': time_sec,
                    'remaining': rem,
                    'frame': frame,
                    'scene': scene_info,
                    'operation': operation,
                    'sample': curr_sample,
                    'mem': {
                        'total': mem_total,
                        'total_peak': mem_total_peak,
                        'render': mem_render,
                        'render_peak': mem_render_peak,
                    },
                })

                if curr_sample == 1:
                    prepare_time = time_sec
                    self.statusPrepareTimeSet(prepare_time)

                # Update preview every 5 second
                if curr_sample > 1 and curr_sample < self._cfg.samples and time.time() > sample_preview_save_time:
                    try:
                        sample_preview_save_time = time.time() + 5
                        process.stdin.write(b'savePreview\n')
                        process.stdin.flush()
                    except Exception as e:
                        print('ERROR: Unable to send "savePreview" command due to exception: %s' % e)

                if operation in ('Finished', 'Cancel | Cancelled'):
                    finished = operation == 'Finished'
                    process.stdin.write(b'end\n')
                    process.stdin.flush()
                    if curr_sample > 1:
                        self.statusRenderTimeSet(time_sec - prepare_time)
                        self.statusSamplesDoneSet(curr_sample if finished else curr_sample-1)

            # Collecting the render statistics
            if l.startswith('Render statistics:'):
                statistics = {}
                header = None
                for line in iter(process.stdout.readline, b''): # Redefined line intentionally
                    l = ''
                    try:
                        l = line.decode('utf-8').rstrip()
                    except LookupError:
                        # UTF-8 not worked, so probably it's latin1
                        l = line.decode('iso-8859-1').rstrip()
                    print(">std>> %s" % l)

                    if not l:
                        break

                    if not l.startswith(' ') and l.endswith(':'):
                        header = l.rstrip(':')
                        statistics[header] = []
                        continue

                    statistics[header].append(l.rstrip())

                for h, d in statistics.items():
                    statistics[h] = '\n'.join(d)

                self.statusStatisticsSet(statistics)

            # Processing task stop
            if self._stop_task and not interrupted:
                interrupted = True
                print('INFO: Stopping the task execution')
                self.executionMessagesAdd('INFO: Stopping the worker process')
                process.send_signal(signal.SIGINT) # Signal will cause Cancel event
                continue

            # Do something on terminating
            if self._parent.isTerminating():
                print('WARN: Detected terminating in %s' % self._parent.timeToTerminating())
                self.executionMessagesAdd('WARN: Instance is going to be terminated in %d sec' % self._parent.timeToTerminating())
                rem = self.status().get('remaining')
                if rem:
                    # Ok some work is here, so need to check how much is remaining
                    # We have just 20 sec to complete - so let's calculate:
                    if rem < self._parent.timeToTerminating() - 10.0:
                        # Looks like we still have time to complete the task
                        continue

                    # We can't do that - so request the render right now and stop the task
                    if not interrupted:
                        interrupted = True
                        print('WARN: Process is going to be cancelled')
                        self.executionMessagesAdd('WARN: Cancelling the worker process')
                        process.send_signal(signal.SIGINT) # Signal will cause Cancel event
                        continue

                # No remaining - no actual work started, so just stop the task
                if not interrupted:
                    interrupted = True
                    print('WARN: Process is going to be destroyed')
                    self.executionMessagesAdd('WARN: Killing the worker process')
                    process.kill() # The worker process will be destroyed
                    break

        print('INFO: Read of process stdout completed')
        try:
            process.communicate(timeout=15)
        except TimeoutExpired:
            print('WARN: Killing the subprocess')
            process.kill()
            process.communicate()

        print('DEBUG: Return code: %s' % process.poll())

        if process.poll() == -9: # OOM kill
            self.stateError({self.name(): 'The worker was killed by Out Of Memory - try to use bigger VM for the Agent'})

        if finished:
            self.stateComplete()

    def _stop(self):
        self._stop_task = True

    def statusPreviewSet(self, blob_id):
        # Delete old blob with result
        with self._status_lock:
            if self._status['result']['preview']:
                self._parent._fc.blobRemove(self._status['result']['preview'])
        super().statusPreviewSet(blob_id)

    def statusRenderSet(self, blob_id):
        # Delete old blob with result
        with self._status_lock:
            if self._status['result']['render']:
                self._parent._fc.blobRemove(self._status['result']['render'])
        super().statusRenderSet(blob_id)
