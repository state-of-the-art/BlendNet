#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Azure Instance

Description: Implementation of the Azure instance
'''

import time

from .. import InstanceProvider

class Instance(InstanceProvider):
    def __init__(self):
        InstanceProvider.__init__(self)

    def timeToTerminating(self):
        '''Seconds to instance terminate'''
        if not self.isTerminating():
            return 24*3600
        return self.timeOfTerminating() - time.time() + 60.0
