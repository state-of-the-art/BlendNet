#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Config

Description: Simple config manager
'''

import threading

class Config:
    '''Base class for config'''
    def __init__(self, parent, init = dict()):
        self._parent = parent
        self._config_lock = threading.Lock()
        self._config = dict()
        # Setup setattr override
        self.__setattr__ = self._setattr
        # Init configs
        self.configsSet(init)

    def __getattr__(self, name):
        if name not in self._defs:
            raise Exception('Config error: unable to access not defined config %s' % name)
        with self._config_lock:
            val = self._config.get(name, self._defs[name].get('default'))
        if callable(val):
            val = val(self)
        return val

    def _setattr(self, name, value):
        conf = self._defs.get(name)
        if not conf:
            raise Exception('Config error: unable to access not defined config %s' % name)
        with self._config_lock:
            if value is None and name in self._config:
                self._config.pop(name)
                return True
        if 'type' not in conf:
            with self._config_lock:
                self._config[name] = value
            return True
        if 'validation' in conf and callable(conf['validation']) and not conf['validation'](self, value):
            return print('WARN: Unable to set config "%s" value "%s" - custom validation failed' % (name, value))
        if not isinstance(value, conf['type']):
            return print('WARN: Unable to set config "%s" with value "%s" - %s is required' % (name, value, conf['type'].__name__))

        val_len = None
        if 'min' in conf or 'max' in conf:
            if conf['type'] == int:
                val_len = value
            elif conf['type'] == str:
                val_len = len(value)

        if val_len is not None:
            if 'min' in conf and val_len < conf['min']:
                return print('WARN: Unable to set config "%s" with value "%s" because it is < %d' % (name, value, conf['min']))
            if 'max' in conf and val_len > conf['max']:
                return print('WARN: Unable to set config "%s" with value "%s" because it is > %d' % (name, value, conf['max']))

        with self._config_lock:
            self._config[name] = value

        return True

    def configsSet(self, configs):
        '''Walk through the defined configs and set configs values'''
        for name, conf in self._defs.items():
            if name in configs:
                self._setattr(name, configs[name])
            elif conf.get('value') is not None:
                self._setattr(name, conf['value'](self) if callable(conf['value']) else conf['value'])

    def configsGet(self):
        '''Returns set configs or defaults if defined'''
        out = dict()
        for name, conf in self._defs.items():
            with self._config_lock:
                if name in self._config:
                    out[name] = self._config[name]
            if name not in out and 'default' in conf:
                out[name] = self.__getattr__(name)

        return out
