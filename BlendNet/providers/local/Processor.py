#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Local Processor

Description: Implementation of the Local processor
'''

import json

from ... import SimpleREST

class Processor:
    @SimpleREST.put('agent/*/config')
    def agent_set_config(self, req, parts):
        '''Set the custom agent configuration as json (max 128KB)'''
        length = req.headers['content-length']
        if not length:
            return { 'success': False, 'message': 'Unable to find "Content-Length" header' }

        if int(length) > 128*1024: # Max 128KB
            return { 'success': False, 'message': 'Unable read too big agent configuration (> 128KB)' }

        conf = None
        try:
            conf = json.loads(req.rfile.read(int(length)))
        except Exception as e:
            return { 'success': False, 'message': 'Error during parsing the json data: %s' % e }

        if self._e.agentGet(parts[0]):
            return { 'success': False, 'message': 'Unable to modify existing agent configs' }

        if not self._e.agentCustomCreate(parts[0], conf):
            return { 'success': False, 'message': 'Error during agent configuration' }

        return { 'success': True, 'message': 'Agent configured' }

    @SimpleREST.delete('agent/*')
    def agent_remove(self, req, parts):
        '''Remove the custom agent from the pool'''
        if not self._e.agentGet(parts[0]):
            return { 'success': False, 'message': 'Unable to find the agent' }

        if not self._e.agentCustomRemove(parts[0]):
            return { 'success': False, 'message': 'Error during removing the agent' }

        return { 'success': True, 'message': 'Agent removed' }
