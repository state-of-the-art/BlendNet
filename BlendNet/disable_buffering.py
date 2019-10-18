#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Disable Buffering

Description: To disable buffering for stdout/stderr
'''

import sys, io

sys.stdout.flush()
sys.stderr.flush()

sys.stdout = sys.__stdout__ = io.TextIOWrapper(
    sys.stdout.detach(),
    encoding = sys.stdout.encoding,
    errors = 'backslashreplace',
    line_buffering = True,
)

sys.stderr = sys.__stderr__ = io.TextIOWrapper(
    sys.stderr.detach(),
    encoding = sys.stdout.encoding,
    errors = 'backslashreplace',
    line_buffering = True,
)

print('DEBUG: Disabled stdout/stderr buffering')
