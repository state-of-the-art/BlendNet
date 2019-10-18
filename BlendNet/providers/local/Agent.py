#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Local Agent

Description: Simple implementation of the local agent
'''

from .. import InstanceProvider

class Agent(InstanceProvider):
    def timeToTerminating(self):
        return 0
