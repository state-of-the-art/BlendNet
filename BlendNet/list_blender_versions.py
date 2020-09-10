#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet module to check the available blender versions

Used in Addon and build automation
Usage: python4 list_blender_versions.py [<version>/lts/latest]
'''

from urllib.request import urlopen
from html.parser import HTMLParser

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

def getBlenderVersions(ctx = None, req_version = None):
    '''Returns a dict with {'<version>': {'url': '<dist_url>', 'checksum': '<sha256>'}}'''
    out = {}
    mirrors = [
        'https://download.blender.org/release/',
        'https://mirror.clarkson.edu/blender/release/',
        'https://ftp.nluug.nl/pub/graphics/blender/release/',
    ]
    for url in mirrors:
        out = {}
        try:
            # Getting the entry point of the mirror
            parser = LinkHTMLParser()
            with urlopen(url, timeout=5, context=ctx) as f:
                parser.feed(f.read().decode())

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

            # Process the versions from latest to oldest
            dirs.reverse()

            # Getting lists of the specific dirs
            for d in dirs:
                with urlopen(url+d, timeout=5, context=ctx) as f:
                    parser.feed(f.read().decode())

                # Processing links of the dirs
                links = parser.links()
                # Process the versions from latest to oldest
                links.reverse()
                for l in links:
                    if not l.endswith('.sha256'):
                        continue
                    # Getting the file and search for linux dist there
                    with urlopen(url+d+l, timeout=5, context=ctx) as f:
                        for line in f:
                            sha256, name = line.decode().strip().split()
                            if '-linux' not in name or '64.tar' not in name:
                                continue
                            ver = name.split('-')[1]
                            if req_version not in {'lts', 'latest', None}:
                                if not ver == req_version:
                                    continue # Check the full version equality
                            out[ver] = {
                                'url': url+d+name,
                                'checksum': sha256,
                            }
                            print('INFO: found blender version: %s (%s %s)' % (ver, url, sha256))
                            if req_version:
                                return out # Return just one found required version

            # Don't need to check the other mirrors
            break

        except Exception as e:
            print('WARN: unable to get mirror list for: %s %s' % (url, e))

    return out


if __name__ == '__main__':
    import sys
    req_version = sys.argv[-1] if len(sys.argv) > 1 else None
    print('INFO: Getting Blender versions with required one: "%s"' % (req_version,))
    versions = getBlenderVersions(None, req_version)
    for ver in versions:
        print('DATA:', ver, versions[ver]['checksum'], versions[ver]['url'])
