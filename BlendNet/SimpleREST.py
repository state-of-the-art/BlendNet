#!/usr/bin/python3.7
# -*- coding: UTF-8 -*-
'''SimpleREST

Description: Implementation of a simple REST interface
'''

import os
import http.server # Multi-threaded http server
import ssl # To protect the communication
import json # Used to produce responses
import urllib.parse # Quote the strings

class ProcessorBase:
    def __init__(self, prefix = 'api/v1'):
        self._prefix = '/'+prefix
        self._path_map = {}
        self._path_doc = {}

    def _initPathMethods(self):
        list_attrs = dir(self)
        for name in list_attrs:
            method = getattr(self, name)
            if callable(method) and hasattr(method, '_method'):
                self._setPathMethod(method)

    def _setPathMethod(self, func):
        print('Adding %s path "%s"' % (func._method.upper(), func._path))
        split_path = [func._method] + func._path.split('/')
        curr = self._path_map
        curr_doc = self._path_doc
        curr_path = []
        while split_path:
            it = split_path.pop(0)
            curr_path.append(it)
            if it not in curr:
                curr[it] = {}
                curr_doc[it] = {}

            curr = curr[it]
            curr_doc = curr_doc[it]

            if not isinstance(curr, dict):
                return print('WARN: Unable to set path "%s" of method %s in type %s' % (func._path, func.__name__, type(curr).__name__))

            if not split_path:
                if '?' in curr:
                    return print('WARN: conflict of path "%s" of method %s with already existing path "%s" of method %s' %
                            (func._path, func.__name__, curr['?']._path, curr['?'].__name__))
                curr['?'] = func
                curr_doc['?'] = func.__doc__

    def _runPathMethod(self, method, req):
        split_path = [method] + req.path.strip('/').split('/')
        curr = self._path_map
        func = None
        parts = []
        while split_path:
            it = split_path.pop(0)
            if it not in curr:
                if '*' in curr:
                    parts.append(it)
                    it = '*'
                elif '**' in curr:
                    parts.append('/'.join([it]+split_path))
                    func = curr['**']['?']
                    break
                else:
                    print('WARN: unable to find path method for path "%s"' % req.path)
                    break

            curr = curr[it]

            if not split_path:
                if '?' not in curr:
                    print('WARN: unable to execution method for path "%s"' % req.path)
                    break
                func = curr['?']
                break

        if not func:
            return self._invalidRequest(req)

        if func.__code__.co_argcount > 2:
            return func(req, parts)
        return func(req)

    def _invalidRequest(self, req):
        return { 'success': False, 'message': 'Invalid request',
            'endpoints': self._getEndpoints(),
        }

    def _getEndpoints(self):
        return self._path_doc

# Create HTTP method decorators
for m in ['get', 'post', 'put', 'patch', 'delete']:
    def _reg(method):
        def _wrap(path = None):
            def _wrapper(func):
                func._method = method
                func._path = path if path else func.__name__
                return func
            return _wrapper
        return _wrap
    globals()[m] = _reg(m)

# Simple methods for certs generation
def generateCA(name):
    '''Generates a new simple certification authority certificate and key'''
    if not os.path.exists('ca.key'):
        os.system('openssl req -newkey rsa:4096 -nodes -keyout ca.key '
                  '-x509 -days 1024 -sha256 -out ca.crt -subj "/C=US/ST=N/L=N/O=N/OU=N/CN={0}-ca"'.format(name))

def generateCert(name, filename):
    '''Generates new simple certificate signed by CA'''
    if not os.path.exists('%s.key' % filename):
        generateCA(name)
        os.system('openssl req -newkey rsa:4096 -nodes -keyout "{1}.key" '
                  '-sha256 -subj "/C=US/ST=N/L=N/O=N/OU=N/CN={0}" -out "{1}.csr"'.format(name, filename))
        os.system('openssl x509 -req -in "{0}.csr" -CA ca.crt -CAkey ca.key -CAcreateserial '
                  '-out "{0}.crt" -days 512 -sha256'.format(filename))

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def send_response(self, code):
        if hasattr(self, '_headers_sent'):
            return
        super().send_response(code)

    def send_header(self, name, value):
        if hasattr(self, '_headers_sent'):
            return
        super().send_header(name, value)

    def end_headers(self):
        if hasattr(self, '_headers_sent'):
            return
        super().end_headers()
        self._headers_sent = True

    def sendHead(self, code = 200):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def sendAuthHead(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="%s"' % urllib.parse.quote(self.server.getName()))
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def checkAuth(self):
        if self.headers.get('Authorization') != self.server.getAuth():
            self.sendAuthHead()
            response = { 'success': False, 'message': 'Invalid credentials' }
            self.wfile.write(bytes(json.dumps(response), 'utf-8'))
            return False
        return True

    def processRequest(self, req_type = 'get'):
        if not self.checkAuth():
            return

        proc = self.server.getProcessor(self.path)
        resp = None
        if proc:
            self.path = self.path[len(proc[0]):]
            resp = proc[1]._runPathMethod(req_type, self)
        else:
            resp = ProcessorBase._invalidRequest(self.server, self)

        if 'success' in resp: # Regular json response
            self.sendHead(200 if resp['success'] else 400)
            self.wfile.write(bytes(json.dumps(resp), 'utf-8'))

    def do_GET(self):
        self.processRequest()

    def do_POST(self):
        self.processRequest('post')

    def do_PUT(self):
        self.processRequest('put')

    def do_PATCH(self):
        self.processRequest('patch')

    def do_DELETE(self):
        self.processRequest('delete')

class HTTPServer(http.server.ThreadingHTTPServer):
    _auth = None
    _ssl_context = None

    def __init__(self, address, name = 'SimpleREST', processors=[ProcessorBase()], handlerClass=RequestHandler):
        self._processors = {}
        self._name = name
        for p in processors:
            p._initPathMethods()
            self._processors[p._prefix] = p
        super().__init__(address, handlerClass)
        print('Serving at', address)

    def _getEndpoints(self):
        return list(self._processors.keys())

    def get_request(self):
        request, agent_address = self.socket.accept()
        if self._ssl_context:
            request = self._ssl_context.wrap_socket(request, server_side=True)
        return request, agent_address

    def getProcessor(self, path):
        processors = {(prefix, proc) for prefix, proc in self._processors.items() if path.startswith(prefix) }
        # Choosing the most suitable processor by prefix
        return None if not processors else sorted(processors, key=len)[0]

    def setBasicAuth(self, auth):
        if auth:
            import base64
            self._auth = 'Basic %s' % base64.b64encode(bytes(auth.strip(), 'utf-8')).decode('ascii')

    def getAuth(self):
        return self._auth

    def setTLS(self, key = None, cert = None):
        '''Setup the connection encryption using TLS'''
        self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        if key and cert:
            import stat
            with open('server.key', 'wb') as f:
                os.chmod('cert.key', stat.S_IRUSR|stat.S_IWUSR|stat.S_IWGRP|stat.S_IRGRP)
                f.write(key.encode())
            with open('server.crt', 'wb') as f:
                f.write(key.encode())

        generateCert(self.getName(), 'server')
        self._ssl_context.load_cert_chain('server.crt', 'server.key')

    def getName(self):
        return self._name
