#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Agent Client

Description: Agent REST client
'''

import json # Used to parse response
from .Client import (
    Client,
    ClientEngine,
)

class AgentClient(Client):
    def __init__(self, address, cfg):
        self._address = address
        self._cfg = cfg
        self._engine = ClientEngine(address, cfg)
