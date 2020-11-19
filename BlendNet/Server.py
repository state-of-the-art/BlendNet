#!/usr/bin/python3.7
# -*- coding: UTF-8 -*-
'''BlendNet Server

Description: Basic REST service for BlendNet task servers
'''

import os, sys, time
import json # Used in the tasks configuration

from . import providers
from . import SimpleREST

class CopyStringIO:
    '''Class to store the logs to get them from client'''
    def __init__(self, orig_out, copy_out):
        self._orig_out = orig_out
        self._copy_out = copy_out
    def write(self, buf):
        self._orig_out.write(buf)
        self._copy_out[time.time()] = buf
        if len(self._copy_out) > 100000:
            to_remove_keys = sorted(self._copy_out.keys())[0:10000]
            for key in to_remove_keys:
                del self._copy_out[key]
    def flush(self):
        self._orig_out.flush()

class Processor(providers.Processor, SimpleREST.ProcessorBase):
    def __init__(self, engine, prefix = 'api/v1'):
        print('DEBUG: Creating Processor')
        providers.Processor.__init__(self)
        SimpleREST.ProcessorBase.__init__(self, prefix)

        self._e = engine
        self._log = dict()

        sys.stdout = CopyStringIO(sys.__stdout__, self._log)
        sys.stderr = CopyStringIO(sys.__stderr__, self._log)

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
            build_date = bpy.app.build_date
            try:
                build_date = build_date.decode('utf-8')
            except LookupError:
                # UTF-8 not worked, so probably it's latin1
                build_date = build_date.decode('iso-8859-1')

            out['data']['blender'] = {
                'version': bpy.app.version,
                'version_string': str(bpy.app.version_string),
                'build_date': build_date,
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

    @SimpleREST.get()
    def log(self, req = None):
        '''Return the captured log'''

        return { 'success': True, 'data': self._log }

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
        if not sha1:
            return { 'success': False, 'message': 'Unable to find file "%s" for task "%s"' % (parts[1], parts[0]) }

        return { 'success': True, 'message': 'Got task file info',
            'data': {
                'id': sha1,
                'path': parts[1],
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
