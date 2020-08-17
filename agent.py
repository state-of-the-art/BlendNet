#!/usr/bin/python3.7
# -*- coding: UTF-8 -*-
'''BlendNet Agent REST

Description: REST interface for Agent
'''

import os, sys
sys.path.append(os.path.dirname(__file__))

from BlendNet import (
    disable_buffering,
    Agent,
    SimpleREST,
    Server,
)

class Processor(Server.Processor):
    def __init__(self, conf, prefix = 'api/v1'):
        super().__init__(Agent(conf), prefix)


# TODO: allow even basic config change - restart the http server if its configs changed
conf = {}
if os.path.exists('agent.json'):
    with open('agent.json', 'r') as f:
        import json
        conf = json.load(f)

SimpleREST.generateCert(conf.get('instance_name', 'blendnet-agent'), 'server')
httpd = SimpleREST.HTTPServer((conf.get('listen_host', ''), conf.get('listen_port', 9443)), __doc__.split('\n')[0], [Processor(conf)])
httpd.setTLS(conf.get('server_tls_key', None), conf.get('server_tls_cert', None))
httpd.setBasicAuth('%s:%s' % (conf.get('auth_user', None), conf.get('auth_password', None)))

httpd.serve_forever()
