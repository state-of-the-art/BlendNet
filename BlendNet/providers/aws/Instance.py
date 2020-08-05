#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''AWS Instance

Description: Implementation of the AWS instance
'''

import time # To sleep threads sometimes
import threading # To watch on the termination status
import urllib.request # To request metadata

from . import METADATA_URL
from .. import InstanceProvider

class Instance(InstanceProvider):
    def __init__(self):
        InstanceProvider.__init__(self)

        self._terminatingWatchersReset()

    def timeToTerminating(self):
        '''Seconds to instance terminate'''
        if not self.isTerminating():
            return 24*3600
        # Actually gives 2 mins according the AWS documentation
        return self.timeOfTerminating() - time.time() + 60.0


    def _terminatingWatchersReset(self):
        '''Reinitialize terminating watchers'''
        if hasattr(self, '_terminating_threads'):
            with self._terminating_lock:
                self._terminating_threads_run = False
            for thread in self._terminating_threads:
                thread.join()

        with self._terminating_lock:
            self._terminating_threads_run = True
            self._terminating = None
            self._terminating_reset_timer = threading.Timer(90, self._terminatingWatchersReset)

        urls = [
            METADATA_URL + 'spot/termination-time',
        ]
        self._terminating_threads = [threading.Thread(target=self._isTerminatingWatch, args=(url,)) for url in urls]
        for thread in self._terminating_threads:
            thread.start()

    def _isTerminatingWatch(self, url):
        print('INFO: Listening on url "%s" for termination status' % url)
        req = urllib.request.Request(url)

        while True:
            with self._terminating_lock:
                if self._terminating or not self._terminating_threads_run:
                    return
            try:
                with urllib.request.urlopen(req, timeout=10) as res:
                    if res.getcode() in {503, 404}:
                        time.sleep(5)
                        continue

                    data = res.read()
                    print('WARN: Found terminating status for url: %s, "%s"' % (url, data))
                    with self._terminating_lock:
                        if not self._terminating:
                            self._terminating_reset_timer.start()
                    self.setTerminating()
                    return
            except:
                pass
