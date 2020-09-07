#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Instance Provider

Description: Abstract class of instance provider methods
'''

import time
import threading # Locks
from abc import ABC, abstractmethod

class InstanceProvider(ABC):
    def __init__(self):
        self._terminating_lock = threading.Lock()
        self._terminating = None

    def isTerminating(self):
        '''The instance is going to shutdown soon'''
        with self._terminating_lock:
            return bool(self._terminating)

    def timeOfTerminating(self):
        '''Timestamp in sec of the terminate signal'''
        with self._terminating_lock:
            return self._terminating

    def setTerminating(self):
        '''Show the current status on instance termination'''
        with self._terminating_lock:
            if self._terminating:
                return
            self._terminating = time.time()

    @abstractmethod
    def timeToTerminating(self):
        '''Seconds to instance terminate'''
        if not self.isTerminating():
            return 24*3600
        return self.timeOfTerminating() - time.time() + 30.0
