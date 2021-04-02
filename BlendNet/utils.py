#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Utils

Description: Common utils for BlendNet
'''

import os
import time
import platform

# Unfortunately built-in python path functions are platform-dependent
# WARNING: Backslash-separated paths on windows will be resolved as separators!
def isPathStraight(path):
    '''Checks that the path contains '..' (parent dir usage) or not'''
    if path.startswith('..') or path.endswith('..') or '/../' in path:
        # Cound lead to false-positives with "..file..", but at least
        # it will check the backslash case too
        return False
    # Just to be sure there will be no backslash issues:
    if '\\..\\' in path:
        return False
    return True

def isPathAbsolute(path):
    '''Will check the path: it's absolute or not in cross-platform way'''
    if path.startswith('/') and not path.startswith('//'):
        return True
    if len(path) > 2 and path[1] == ':' and path[2] == '/':
        # For now supports only general one-letter windows disks
        return True
    return isPathLinAbsolute(path) or isPathWinAbsolute(path)

def isPathLinAbsolute(path):
    '''Will check the path: it's absolute for linux path'''
    return path.startswith('/') and not path.startswith('//')

def isPathWinAbsolute(path):
    '''Will check the path: it's absolute for windows path'''
    # For now supports only general one-letter windows disks
    return len(path) > 2 and path[1] == ':' and path[2] in ('/', '\\')

def resolvePath(path):
    '''Will make sure all the parent dirs are resolved'''
    # There is no proper way to resolve win paths on linux and vice versa
    if platform.system() == 'Windows' and not isPathWinAbsolute(path):
        return os.path.abspath('C:/'+path)[3:].replace('\\', '/')
    elif platform.system() != 'Windows' and not isPathLinAbsolute(path):
        return os.path.abspath('/'+path)[1:]
    else:
        return os.path.abspath(path)

class CopyStringIO:
    '''Class to store the logs to get them with timestamps later'''
    def __init__(self, orig_out, copy_out, copy_out_lock):
        self._orig_out = orig_out
        self._copy_out = copy_out
        self._copy_out_lock = copy_out_lock
    def write(self, buf):
        self._orig_out.write(buf)
        with self._copy_out_lock:
            key = str(time.time())
            while key in self._copy_out:
                key = str(float(key)+0.00001)
            self._copy_out[key] = buf
            if len(self._copy_out) > 100000:
                to_remove_keys = sorted(self._copy_out.keys())[0:10000]
                for key in to_remove_keys:
                    del self._copy_out[key]
    def flush(self):
        self._orig_out.flush()

    def isatty(self):
        return self._orig_out.isatty()
