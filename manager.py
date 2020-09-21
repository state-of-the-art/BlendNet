#!/usr/bin/python3.7
# -*- coding: UTF-8 -*-
'''BlendNet Manager REST

Description: REST interface for Manager
Run: /srv/blender/blender -b -noaudio -P /srv/blendnet/manager.py
'''

import os, sys
sys.path.append(os.path.dirname(__file__))

from BlendNet import (
    disable_buffering,
    Manager,
    SimpleREST,
    Server,
    providers,
)

class Processor(Server.Processor):
    def __init__(self, conf, prefix = 'api/v1'):
        super().__init__(Manager(conf), prefix)

    @SimpleREST.get('resources')
    def resources(self, req = None):
        '''Returns the available resources'''

        return {
            'success': True,
            'message': 'Resources got',
            'data': self._e.resourcesGet(),
        }

    @SimpleREST.get('agent/*/log')
    def agent_log(self, req, parts):
        '''Returns the information about the task'''
        agent = self._e.agentGet(parts[0])
        if not agent:
            return { 'success': False, 'message': 'Unable to find agent' }

        data = agent.log()
        if not data:
            return { 'success': False, 'message': 'No data received from the agent' }

        return { 'success': True, 'message': 'Got agent log', 'data': data }


# TODO: allow even basic config change - restart the http server if its configs changed
conf = {}
if os.path.exists('manager.json'):
    with open('manager.json', 'r') as f:
        import json
        conf = json.load(f)

SimpleREST.generateCert(conf.get('instance_name', 'blendnet-manager'), 'server')
httpd = SimpleREST.HTTPServer((conf.get('listen_host', ''), conf.get('listen_port', 8443)), __doc__.split('\n')[0], [Processor(conf)])
httpd.setTLS(conf.get('server_tls_key', None), conf.get('server_tls_cert', None))
httpd.setBasicAuth('%s:%s' % (conf.get('auth_user', None), conf.get('auth_password', None)))

# Upload CA back to the blendnet bucket
if os.path.exists('ca.crt') and conf.get('bucket'):
    providers.uploadFileToBucket('ca.crt', conf.get('bucket'))

httpd.serve_forever()
