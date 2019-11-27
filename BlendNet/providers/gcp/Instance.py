#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''GCP Instance

Description: Implementation of the GCP instance
'''

import time # To sleep threads sometimes
import threading # To watch on the termination status
import urllib.request # To request metadata

from . import METADATA_URL, METADATA_HEADER
from .. import InstanceProvider

class Instance(InstanceProvider):
    def __init__(self):
        InstanceProvider.__init__(self)

        self._terminatingWatchersReset()

    def timeToTerminating(self):
        '''Seconds to instance terminate'''
        if not self.isTerminating():
            return 24*3600
        # Not working well - sometimes instances terminating earlier
        #return self.timeOfTerminating() - time.time() + 30.0
        return self.timeOfTerminating() - time.time()


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
            ( '%sinstance/preempted?wait_for_change=true&timeout_sec=5' % (METADATA_URL), b'FALSE' ),
            ( '%sinstance/maintenance-event?wait_for_change=true&timeout_sec=5' % (METADATA_URL), b'NONE' ),
        ]
        self._terminating_threads = [threading.Thread(target=self._isTerminatingWatch, args=(url, ok_result)) for url, ok_result in urls]
        for thread in self._terminating_threads:
            thread.start()

    def _isTerminatingWatch(self, url, ok_result):
        print('INFO: Listening on url "%s" for termination status' % url)
        req = urllib.request.Request(url)
        req.add_header(*METADATA_HEADER)

        while True:
            with self._terminating_lock:
                if self._terminating or not self._terminating_threads_run:
                    return
            try:
                with urllib.request.urlopen(req, timeout=10) as res:
                    if res.getcode() == 503:
                        time.sleep(1)
                        continue

                    data = res.read(len(ok_result))
                    if data == ok_result:
                        continue

                    print('WARN: Found terminating status for url: %s, "%s"' % (url, data))
                    with self._terminating_lock:
                        if not self._terminating:
                            self._terminating_reset_timer.start()
                    self.setTerminating()
                    return
            except:
                pass
