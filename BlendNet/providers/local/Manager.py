#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Local Manager

Description: Implementation of the Local manager
'''

from .. import InstanceProvider

class Manager(InstanceProvider):
    def timeToTerminating(self):
        return 0
