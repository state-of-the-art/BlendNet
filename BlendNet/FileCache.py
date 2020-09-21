#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''FileCache

Description: Class to receive, store and clean data on the file system
'''

import os
import tempfile # To get the temp directory
import time # We need timestamps
import json # To read/save the blob metadata
import hashlib # Confirm sha1 hash of the blob
import threading # Using locks for multi-threading streaming
import shutil # Useful recursive dir remove feature
import re # Used to clean bad symbols for tmp files

class FileCache:
    def __init__(self, path = None, name = None):
        if not path:
            path = tempfile.gettempdir()
            print('WARN: using a temp dir to store cache "%s"' % path)

        if not name:
            name = self.__class__.__name__

        # Ensure tmp files will be ok
        self._safe_pattern = re.compile('[\\W_]+', re.UNICODE)

        self._cache_dir = os.path.abspath(os.path.join(path, name))
        os.makedirs(self._cache_dir, 0o700, True)
        self._blobs_dir = os.path.join(self._cache_dir, 'blobs')
        os.makedirs(self._blobs_dir, 0o700, True)
        self._tmp_dir = os.path.join(self._cache_dir, 'tmp')
        os.makedirs(self._tmp_dir, 0o700, True)

        self._workspace_dir = os.path.join(self._cache_dir, 'ws')
        if os.path.exists(self._workspace_dir):
            shutil.rmtree(self._workspace_dir)
        os.makedirs(self._workspace_dir, 0o700, True)
        self._workspace_blobs = {} # Stores blobs used per workspace

        print('INFO: using the cache directory "%s"' % self._cache_dir)

        self._write_cache_timer_lock = threading.Lock()
        self._write_cache_timer = None
        self._blobs_map_lock = threading.Lock()
        self.readCache()

        # Uploading could be multithreaded - so we need to free space properly
        self._required_space = 0
        self._required_space_lock = threading.Lock()

    def readCache(self):
        '''Fill the file map from the existing cache directory'''
        self._last_save_time = int(time.time())

        with self._blobs_map_lock:
            self._blobs_map = {}
        blobs_dirs = os.listdir(self._blobs_dir)
        if not blobs_dirs:
            return

        print('INFO: Reading blobs metadata from disk')
        for d in blobs_dirs:
            bd = os.path.join(self._blobs_dir, d)
            with os.scandir(bd) as it:
                for entry in it:
                    if not (entry.is_file() and entry.name.endswith('.json')):
                        continue
                    info = entry.name.split('.')
                    json_path = os.path.join(bd, entry.name)
                    try:
                        with open(json_path, 'r') as f:
                            with self._blobs_map_lock:
                                self._blobs_map[info[0]] = json.load(f)
                    except:
                        print('ERROR: Unable to parse metadata from disk: %s' % json_path)

        with self._blobs_map_lock:
            print('INFO: Found %i blobs in cache' % len(self._blobs_map))

    def writeCache(self):
        with self._write_cache_timer_lock:
            if self._write_cache_timer:
                return
            self._write_cache_timer = threading.Timer(10, self._writeCache)
            self._write_cache_timer.start()

    def _writeCache(self):
        '''Save recently accessed blobs metadata'''
        changed_blobs = None
        with self._blobs_map_lock:
            changed_blobs = [data.copy() for _, data in self._blobs_map.items() if data['access_time'] > self._last_save_time]
        if not changed_blobs:
            return

        print('INFO: Writing %i changed blobs metadata to disk' % len(changed_blobs))

        for blob in changed_blobs:
            if 'id' not in blob:
                continue
            blob_dir = os.path.join(self._blobs_dir, blob['id'][0:2])
            os.makedirs(blob_dir, 0o700, True)
            with open(os.path.join(blob_dir, blob['id']+'.json'), 'w') as f:
                json.dump(blob, f)

        self._last_save_time = int(time.time())
        with self._write_cache_timer_lock:
            self._write_cache_timer = None

    def blobGet(self, sha1):
        '''Get blob and return info or return None'''
        with self._blobs_map_lock:
            if sha1 in self._blobs_map:
                return self._blobs_map[sha1].copy()
        return None

    def blobGetStream(self, sha1):
        '''Return stream of the blob'''
        sha1 = self._safe_pattern.sub('', sha1)
        blob_path = os.path.join(self._blobs_dir, sha1[0:2], sha1)
        if not os.path.exists(blob_path):
            return print('ERROR: Unable to serve stream of not existing blob "%s"' % sha1)
        return open(blob_path, 'rb')

    def blobUpdate(self, sha1, data = dict()):
        '''Set data in the blob'''
        t = int(time.time())
        with self._blobs_map_lock:
            if sha1 not in self._blobs_map:
                self._blobs_map[sha1] = {
                    'create_time': t,
                }
            self._blobs_map[sha1].update(data)
            self._blobs_map[sha1]['access_time'] = t
            self.writeCache()

            return self._blobs_map[sha1].copy()

    def blobRemove(self, sha1):
        '''Removes blob and metadata from disk and returns True on success'''
        print('INFO: Removing blob "%s"' % sha1)
        blob_dir = os.path.join(self._blobs_dir, sha1[0:2])
        blob_path = os.path.join(blob_dir, sha1)
        json_path = blob_path+'.json'

        try:
            if os.path.exists(blob_path):
                os.remove(blob_path)
            if os.path.exists(json_path):
                os.remove(json_path)
        except Exception as e:
            # Could happen on Windows if file is used by some process
            print('ERROR: Unable to remove blob file:', str(e))
            return False

        with self._blobs_map_lock:
            if sha1 not in self._blobs_map:
                return
            self._blobs_map.pop(sha1)

        return True

    def cleanOldCache(self, size = None):
        '''Clean old blobs to free `size` of cache space'''
        print('INFO: Cleaning %s bytes of cache' % size)
        oldest_blobs = None
        with self._blobs_map_lock:
            oldest_blobs = sorted([d.copy() for _, d in self._blobs_map.items() if 'id' in d], key=lambda v: v['access_time'])

        size_cleaned = 0
        removed_blobs = 0
        for blob in oldest_blobs:
            if size and size_cleaned >= size:
                break
            # Skip important (dnd - do not delete) and workspace blobs
            used = self._workspace_blobs.copy()
            if blob.get('dnd') or blob['id'] in { item for key in used for item in used[key] }:
                continue
            size_cleaned += blob['size']
            self.blobRemove(blob['id'])
            removed_blobs += 1

        print('INFO: Cleaned %i blobs and %i bytes' % (removed_blobs, size_cleaned))

    def freeSpace(self, size):
        '''Ensure there is a free space on the disk to store the file of `size`'''
        cur_req_space = 0
        with self._required_space_lock:
            self._required_space += size
            cur_req_space = self._required_space - self.getAvailableSpace()

        if cur_req_space <= 0:
            return True

        self.cleanOldCache(cur_req_space)

        with self._required_space_lock:
            return self.getAvailableSpace() >= self._required_space

    def _receivedData(self, size):
        '''Will sub amount of received bytes from planned'''
        with self._required_space_lock:
            self._required_space -= size

    def _receiveStream(self, stream, size, tmp_name):
        '''Unified function to receive stream and calculate sha1 id'''
        tmp_path = os.path.join(self._tmp_dir, self._safe_pattern.sub('', tmp_name))
        sha1_calc = hashlib.sha1()
        size_left = size
        try:
            with open(tmp_path, 'wb') as f:
                for chunk in iter(lambda: stream.read(min(1048576, size_left)), b''):
                    sha1_calc.update(chunk)
                    f.write(chunk)
                    self._receivedData(len(chunk))
                    size_left -= len(chunk)
            return sha1_calc.hexdigest(), tmp_path
        except Exception as e:
            self._receivedData(size_left)
            try:
                os.remove(tmp_path)
            except Exception as e:
                # Could happen on Windows if file is used by some process
                print('ERROR: Unable to remove temp file:', str(e))
            return print('ERROR: Unable to receive stream due to exception: %s' % e)

    def blobStoreStream(self, stream, size, sha1, important = False):
        '''Store stream as blob in the cache'''
        blob = self.blobUpdate(sha1)
        if 'id' in blob:
            return blob

        if not self.freeSpace(size):
            return print('WARN: Unable to find the available space for the file')

        received = self._receiveStream(stream, size, sha1)
        if not received:
            self.blobRemove(sha1)
            return print('ERROR: Unable to read stream')

        if sha1 != received[0]:
            return print('WARN: Wrong sha1 sum for received stream "%s"' % received[0])

        # Moving tmp file into the blobs directory
        blob_dir = os.path.join(self._blobs_dir, sha1[0:2])
        os.makedirs(blob_dir, 0o700, True)
        blob_path = os.path.join(blob_dir, sha1)
        try:
            # Windows will not just replace the file - so need to check if it's exist
            if os.path.exists(blob_path):
                os.remove(blob_path)
            os.rename(received[1], blob_path)
        except Exception as e:
            # Could happen on Windows if file is used by some process
            print('ERROR: Unable to move file:', str(e))

        return self.blobUpdate(sha1, {
            'id': sha1,
            'dnd': important,
            'size': size,
        })

    def blobStoreFile(self, path, important = False):
        '''Store local file as blob in the cache'''

        if not os.path.isfile(path):
            return print('ERROR: Unable to store not existing file as blob')

        size = os.stat(path).st_size
        if not self.freeSpace(size):
            return print('WARN: Unable to find the available space for the file')

        received = None
        with open(path, 'rb') as f:
            received = self._receiveStream(f, size, path)
        if not received:
            return print('ERROR: Unable to read stream')

        blob = self.blobUpdate(received[0])
        if 'id' in blob:
            return blob

        # Moving tmp file into the blobs directory
        blob_dir = os.path.join(self._blobs_dir, received[0][0:2])
        os.makedirs(blob_dir, 0o700, True)
        blob_path = os.path.join(blob_dir, received[0])
        try:
            # Windows will not just replace the file - so need to check if it's exist
            if os.path.exists(blob_path):
                os.remove(blob_path)
            os.rename(received[1], blob_path)
        except Exception as e:
            # Could happen on Windows if file is used by some process
            print('ERROR: Unable to move file:', str(e))

        return self.blobUpdate(received[0], {
            'id': received[0],
            'dnd': important,
            'size': size,
        })

    def getTotalSpace(self):
        '''Total cache space in bytes'''
        res = os.statvfs(self._cache_dir)
        return res.f_frsize * res.f_blocks

    def getAvailableSpace(self):
        '''Available cache space in bytes'''
        res = os.statvfs(self._cache_dir)
        return res.f_frsize * res.f_bavail

    def workspaceCreate(self, name, files_map):
        '''Creating new workspace and link the provided files into'''
        ws_dir = tempfile.TemporaryDirectory(suffix=name, dir=self._workspace_dir)
        if not ws_dir:
            return print('ERROR: Unable to create new workspace dir for "%s" in "%s"' % (name, self._workspace_dir) )

        self._workspace_blobs[name] = []

        for f, blob in files_map.items():
            if not self.blobGet(blob):
                ws_dir.cleanup()
                self.workspaceClean(name)
                return print('ERROR: Unable to find the required blob "%s" for file "%s"' % (blob, f))
            filepath = os.path.join(ws_dir.name, f)
            dirpath = os.path.dirname(filepath)
            if not os.path.isdir(dirpath):
                os.makedirs(dirpath, 0o700, True)

            os.link(os.path.join(self._blobs_dir, blob[0:2], blob), filepath)
            self._workspace_blobs[name].append(blob)

        return ws_dir

    def workspaceClean(self, name):
        '''Cleans blobs locks used in the workspace'''
        self._workspace_blobs.pop(name)
