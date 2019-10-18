#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Script Merge

Description: Special script used by the Manager to merge results
'''

import signal # The other better ways are not working for subprocess...
signal.signal(signal.SIGTERM, lambda s, f: print('WARN: Dodged TERM subprocess'))

import os, sys, json
sys.path.append(os.path.dirname(__file__))

import disable_buffering

# Read current task specification from json file
task = None
with open(sys.argv[-1], 'r') as f:
    task = json.load(f)

import _cycles
_cycles.merge(
    input = task.get('images', []),
    output = task.get('result', 'result.exr'),
)
