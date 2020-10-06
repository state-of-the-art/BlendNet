#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Workers

Description: Multithread worker
'''

import threading # Sync between threads needed
import queue

class Workers(object):
    def __init__(self, name, max_workers, worker_func):
        print('DEBUG: Creating Workers "%s"' % name)
        self._enabled = True
        self._name = name

        self._to_process = queue.Queue()

        self._tasks_lock = threading.Lock()
        self._tasks_added = 0
        self._tasks_ended = 0
        self._tasks_failed = []

        self._max_workers = max_workers
        self._workers = []

        self._worker_func = worker_func

    def __del__(self):
        print('DEBUG: Deleting Workers "%s"' % self._name)
        self.stop()

    def _workerThread(self):
        '''Simple worker that gets data from queue and feeds the function with it'''
        while self._enabled:
            try:
                data = self._to_process.get(True, 0.1)
                try:
                    result = self._worker_func(*data)
                except Exception as e:
                    print('ERROR: Exception occurred during worker "%s" execution with data %s: %s' % (self._name, data, e))
                    result = e

                if result is not None:
                    with self._tasks_lock:
                        self._tasks_failed.append(result)

                self._to_process.task_done()
                with self._tasks_lock:
                    self._tasks_ended += 1
            except queue.Empty:
                #print('DEBUG: Workers "%s" worker thread completed' % (self._name,))
                break # Thread will stop if there is no tasks

    def start(self):
        '''Will start the workers'''
        self._enabled = True

        for i in range(self._max_workers):
            if len(self._workers) > i:
                if not self._workers[i].is_alive():
                    thread = threading.Thread(target=self._workerThread)
                    thread.start()
                    self._workers[i] = thread
            else:
                thread = threading.Thread(target=self._workerThread)
                thread.start()
                self._workers.append(thread)

    def stop(self):
        '''Will stop all the processing and wait for completion of current processing'''
        if not self._enabled:
            return

        self._enabled = False
        for w in self._workers:
            try:
                w.join()
            except RuntimeError:
                pass # If thread already was terminated

        self._workers.clear()

    def wait(self):
        '''Wait untill all the items will be processed'''
        self._to_process.join()
        return len(self._tasks_failed) == 0

    def add(self, *data):
        '''Just adds data to process'''
        with self._tasks_lock:
            self._tasks_added += 1
        self._to_process.put(data)

    def addSet(self, data_set):
        '''Adds set of data to process by workers and run the process'''
        with self._tasks_lock:
            self._tasks_added += len(data_set)
        for data in data_set:
            self._to_process.put(data)
        self.start()

    def tasksAdded(self):
        '''Returns number of tasks completed'''
        with self._tasks_lock:
            return self._tasks_added

    def tasksEnded(self):
        '''Returns number of tasks ended somehow'''
        with self._tasks_lock:
            return self._tasks_ended

    def tasksFailed(self):
        '''Returns list of results of tasks failed during execution'''
        with self._tasks_lock:
            return self._tasks_failed

    def tasksLeft(self):
        '''Returns number of tasks completed'''
        with self._tasks_lock:
            return self._tasks_added - self._tasks_ended
