#!/usr/bin/python3.7
# -*- coding: UTF-8 -*-
'''BlendNet Server

Description: Basic REST service for BlendNet task servers
'''

import os, sys
import json # Used in the tasks configuration

from . import SimpleREST

class Processor(SimpleREST.ProcessorBase):
    def __init__(self, engine, prefix = 'api/v1'):
        super().__init__(prefix)

        self._e = engine

    @SimpleREST.get()
    def info(self, req = None):
        '''Return information about the server system'''
        import platform

        out = { 'success': True, 'data': {
            'engine': type(self._e).__name__,
            'platform': {
                'python_info': sys.version,
                'system': str(platform.system()),
                'arch': str(platform.machine()),
                'name': str(platform.node()),
                'details': str(platform.platform()),
                'cpu': os.cpu_count(),
            },
        }}

        # If running in blender - show it's info
        try:
            import bpy
            out['blender'] = {
                'version': bpy.app.version,
                'version_string': str(bpy.app.version_string),
                'build_date': bpy.app.build_date.decode('utf-8'),
                'render_threads': bpy.context.scene.render.threads,
            }
        except:
            pass

        return out

    @SimpleREST.get()
    def status(self, req = None):
        '''Returns the current status of the server'''

        return { 'success': True, 'data': {
            'load': self._e.getLoadStatus(),
            'memory': self._e.getMemoryStatus(),
            'disk': self._e.getDiskStatus(),
            'running': [ t.name() for t in self._e.tasksRunning() ],
            'terminating': self._e.isTerminating(),
        }}

    @SimpleREST.get('task')
    def tasks(self, req):
        '''Returns list of existing tasks on the server'''
        tasks = dict([ (n, t.info()) for n, t in self._e.tasks().items() ])
        return { 'success': True, 'message': 'Got tasks info', 'data': tasks }

    @SimpleREST.get('task/*')
    def task(self, req, parts):
        '''Returns the information about the task'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        task = self._e.taskGet(parts[0])

        return { 'success': True, 'message': 'Got task info', 'data': task.info() }

    @SimpleREST.get('task/*/file')
    def task_file_list(self, req, parts):
        '''Returns the information about the task file list'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        return { 'success': True, 'message': 'Got task files list',
            'data': self._e.taskGet(parts[0]).filesGet()
        }

    @SimpleREST.get('task/*/file/**')
    def task_file_info(self, req, parts):
        '''Returns the information about the task file'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        sha1 = self._e.taskGet(parts[0]).fileGet(parts[1])
        if not f:
            return { 'success': False, 'message': 'Unable to find file "%s" for task "%s"' % (path, task) }

        return { 'success': True, 'message': 'Got task file info',
            'data': {
                'id': f,
                'path': path,
                'blob': self._e.blobGet(sha1),
            },
        }

    @SimpleREST.put('task/*/file/**')
    def put_task_file(self, req, parts):
        '''Upload file required to execute task'''
        length = req.headers['content-length']
        if not length:
            return { 'success': False, 'message': 'Unable to find "Content-Length" header' }

        sha1 = req.headers['x-checksum-sha1']
        if not sha1:
            return { 'success': False, 'message': 'Unable to find "X-Checksum-Sha1" header' }

        task = self._e.taskGet(parts[0])
        if not task.canBeChanged():
            return { 'success': False, 'message': 'Unable to upload files for the executing task' }

        result = self._e.blobStoreStream(req.rfile, int(length), sha1)
        if not result:
            return { 'success': False, 'message': 'Error during receiving the file' }

        if not task.fileAdd(parts[1], result['id']):
            return { 'success': False, 'message': 'Error during add file to the task' }

        return { 'success': True, 'message': 'Uploaded task file',
            'data': result,
        }

    @SimpleREST.put('task/*/config')
    def task_set_config(self, req, parts):
        '''Set the configuration of task as json (max 512KB)'''
        length = req.headers['content-length']
        if not length:
            return { 'success': False, 'message': 'Unable to find "Content-Length" header' }

        if int(length) > 512*1024: # Max 512KB
            return { 'success': False, 'message': 'Unable read too big task configuration (> 512KB)' }

        conf = None
        try:
            conf = json.loads(req.rfile.read(int(length)))
        except Exception as e:
            return { 'success': False, 'message': 'Error during parsing the json data: %s' % e }
        
        if not self._e.taskGet(parts[0]).configsSet(conf):
            return { 'success': False, 'message': 'Error during task configuration' }

        return { 'success': True, 'message': 'Task configured' }

    @SimpleREST.get('task/*/run')
    def task_run(self, req, parts):
        '''Mark task as ready to be executed'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        if not self._e.taskGet(parts[0]).run():
            return { 'success': False, 'message': 'Unable to run task' }

        return { 'success': True, 'message': 'Task started' }

    @SimpleREST.get('task/*/status')
    def task_status(self, req, parts):
        '''Return execution status information of the task'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        status = self._e.taskGet(parts[0]).status()

        return { 'success': True, 'message': 'Got task status info', 'data': status }

    @SimpleREST.get('task/*/status/result/*')
    def task_result_stream(self, req, parts):
        '''Streams the task result image for preview or render'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        result = self._e.taskGet(parts[0]).status()['result'].get(parts[1])
        if not result:
            return { 'success': False, 'message': 'No result available' }

        blob = self._e.blobGet(result)
        if not blob:
            return { 'success': False, 'message': 'Unable to find result blob' }

        req.send_response(200)
        req.send_header('Content-Type', 'image/x-exr')
        req.send_header('Content-Length', blob['size'])
        req.send_header('X-Checksum-Sha1', blob['id'])
        req.end_headers()

        with self._e.blobGetStream(blob['id']) as stream:
            for chunk in iter(lambda: stream.read(1048576), b''):
                req.wfile.write(chunk)

        return {}

    @SimpleREST.get('task/*/details')
    def task_execution_details(self, req, parts):
        '''Return detailed execution information about the task'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        return { 'success': True, 'message': 'Got task execution details',
            'data': self._e.taskGet(parts[0]).executionDetailsGet()
        }

    @SimpleREST.get('task/*/messages')
    def task_messages(self, req, parts):
        '''Return execution messages of the task'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        return { 'success': True, 'message': 'Got task execution messages',
            'data': self._e.taskGet(parts[0]).executionMessagesGet()
        }

    @SimpleREST.get('task/*/stop')
    def task_stop(self, req, parts):
        '''Stop the task execution'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        return { 'success': True, 'message': 'Task stopped',
            'data': self._e.taskGet(parts[0]).stop()
        }

    @SimpleREST.delete('task/*')
    def task_remove(self, req, parts):
        '''Remove not running task from the task list'''
        if not self._e.taskExists(parts[0]):
            return { 'success': False, 'message': 'Unable to find task' }

        if self._e.taskGet(parts[0]).isRunning():
            return { 'success': False, 'message': 'Unable to remove the running task' }

        return { 'success': True, 'message': 'Task removed',
            'data': self._e.taskRemove(parts[0])
        }
