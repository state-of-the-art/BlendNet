#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet module to check the available blender versions

Used in Addon and build automation
Usage: python3 list_blender_versions.py [platform [<version>/lts/latest]]
'''

import os
from urllib.request import urlopen
from html.parser import HTMLParser
import threading # Sync between threads needed
try:
    from .Workers import Workers
except ImportError:
    # In case loaded as a regular script
    from Workers import Workers

workers_out = {}
workers_out_lock = threading.Lock()

def _downloadWorker(url, ctx, req_version, req_platform):
    if not url.endswith('.sha256'):
        # Process directory list
        parser = LinkHTMLParser()
        with urlopen(url, timeout=5, context=ctx) as f:
            data = f.read()
            try:
                parser.feed(data.decode('utf-8'))
            except (LookupError, UnicodeDecodeError):
                # UTF-8 not worked, so probably it's latin1
                parser.feed(data.decode('iso-8859-1'))

        # Processing links of the dirs
        links = parser.links()
        global workers
        for link in links:
            if link.endswith('.sha256'):
                workers.add(url+link, ctx, req_version, req_platform)
        workers.start()
        return

    # Process sha256 file data
    # Getting the file and search for linux dist there
    with urlopen(url, timeout=5, context=ctx) as f:
        for line in f:
            try:
                line = line.decode('utf-8')
            except (LookupError, UnicodeDecodeError):
                # UTF-8 not worked, so probably it's latin1
                line = line.decode('iso-8859-1')
            sha256, name = line.strip().split()

            # Check the required platform
            if req_platform == 'lin' and ('-linux' not in name or '64.tar' not in name):
                # blender-2.80-linux-glibc217-x86_64.tar.bz2
                # blender-2.83.7-linux64.tar.xz
                continue
            elif req_platform == 'win' and '-windows64.zip' not in name:
                # blender-2.80-windows64.zip
                # blender-2.83.7-windows64.zip
                continue
            elif req_platform == 'mac' and '-macOS.dmg' not in name:
                # blender-2.80-macOS.dmg
                # blender-2.83.7-macOS.dmg
                continue

            # Check the full version equality
            ver = name.split('-')[1]
            if req_version not in {'lts', 'latest', None}:
                if not ver == req_version:
                    continue

            global workers_out, workers_out_lock
            with workers_out_lock:
                workers_out[ver] = {
                    'url': os.path.dirname(url)+'/'+name,
                    'checksum': sha256,
                }
            print('INFO: found blender version: %s (%s %s)' % (ver, workers_out[ver]['url'], sha256))

workers = Workers(
    'Get the list of available Blender versions',
    8,
    _downloadWorker,
)

class LinkHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._links = []

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        for attr in attrs:
            if attr[0] == 'href':
                self._links.append(attr[1])

    def links(self):
        out = self._links
        self._links = []
        return out

def getBlenderVersions(ctx = None, req_platform = 'lin', req_version = None):
    '''
    * ctx - SSL context to override the CA list
    * req_version - what kind of version to use: strict version, 'lts' or 'latest'
    * req_platform - platform to find the right dist: 'lin', 'win' or 'mac'
    Returns a dict with {'<version>': {'url': '<dist_url>', 'checksum': '<sha256>'}}'''
    mirrors = [
        'https://download.blender.org/release/',
        'https://mirror.clarkson.edu/blender/release/',
        'https://ftp.nluug.nl/pub/graphics/blender/release/',
    ]
    for url in mirrors:
        try:
            # Getting the entry point of the mirror
            parser = LinkHTMLParser()
            with urlopen(url, timeout=5, context=ctx) as f:
                data = f.read()
                try:
                    parser.feed(data.decode('utf-8'))
                except (LookupError, UnicodeDecodeError):
                    # UTF-8 not worked, so probably it's latin1
                    parser.feed(data.decode('iso-8859-1'))

            # Processing links of the first layer
            links = parser.links()
            dirs = []
            for l in links:
                if not l.startswith('Blender') and 'Benchmark' not in l:
                    continue
                ver = ''.join(c for c in l if c.isdigit())
                if int(ver[:2]) < 28:
                    continue # Skip because only >= 2.80 is supported
                if req_version not in {'latest', None}:
                    # Latest will be processed later
                    if req_version == 'lts':
                        # Blender have quite weird LTS numeration, so hardcode here:
                        # https://www.blender.org/download/lts/
                        if not (ver.startswith('283') or
                                ver.startswith('293') or
                                ver.startswith('33') or
                                ver.startswith('37')):
                            continue
                    elif ver != ''.join(req_version.split('.')[:2]):
                        continue # Skip if it's not the required version major.minor
                dirs.append(l)

            # Getting lists of the specific dirs
            for d in dirs:
                workers.add(url+d, ctx, req_version, req_platform)
            workers.start()
            workers.wait()

            if req_version in {'latest', 'lts'}:
                # Getting the latest version - lts was already filtered
                global workers_out
                key = sorted(workers_out.keys())[-1]
                workers_out = {key: workers_out[key]}

            # Don't need to check the other mirrors
            break

        except Exception as e:
            print('WARN: unable to get mirror list for: %s %s' % (url, e))

    return workers_out


if __name__ == '__main__':
    import sys
    req_platform = sys.argv[1] if len(sys.argv) > 1 else 'lin'
    req_version = sys.argv[2] if len(sys.argv) > 2 else None
    print('INFO: Getting Blender versions with required one: "%s" for platform %s' % (req_version, req_platform))
    versions = getBlenderVersions(None, req_platform, req_version)
    for ver in versions:
        print('DATA:', ver, versions[ver]['checksum'], versions[ver]['url'])
