#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Utils

Description: Common utils for BlendNet
'''

import os
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
