#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Manager Client

Description: Manager REST client
'''

import os

from .Client import (
    Client,
    ClientEngine,
)

class ManagerClient(Client):
    _engine = None

    def __init__(self, address, cfg):
        if not ManagerClient._engine:
            ManagerClient._engine = ClientEngine(address, cfg)
        else:
            ManagerClient._engine._address = address
            ManagerClient._engine._cfg = cfg

    def calculateChecksum(self, stream):
        '''Will calculate and redurn checksum and reset stream'''
        import hashlib
        sha1_calc = hashlib.sha1()
        for chunk in iter(lambda: stream.read(1048576), b''):
            sha1_calc.update(chunk)
        stream.seek(0)
        return sha1_calc.hexdigest()

    def taskFilePut(self, task, file_path, rel_path):
        '''Send file to the task file'''
        if not os.path.isfile(file_path):
            print('ERROR: Unable to send not existing file "%s"' % file_path)
            return None

        size = os.path.getsize(file_path)

        with open(file_path, 'rb') as f:
            return self.taskFileStreamPut(task, rel_path, f, size, self.calculateChecksum(f))

    def taskResultDownload(self, task, result, out_path):
        '''Will download result name (preview/render) into the file'''
        return self._engine.download('task/%s/status/result/%s' % (task, result), out_path)
