#!/usr/bin/python3.7
# -*- coding: UTF-8 -*-
'''BlendNet Manager REST v0.1

Description: REST interface for Manager
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
