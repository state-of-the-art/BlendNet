#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Blender Addon UI functions
'''

import os
import bpy
import time
import threading
import hashlib
import ssl
import site
import random
import string
import tempfile
from urllib.request import urlopen
from html.parser import HTMLParser
from datetime import datetime

from . import providers
from . import ManagerClient
from .Workers import Workers

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

def selectProvider(provider):
    '''Sets the current provider identifier'''
    print('DEBUG: selected provider: %s' % provider)
    providers.selectProvider(provider)

def getProvider():
    '''Returns the current provider identifier'''
    return providers.selected_provider

def hidePassword(obj, prop):
    '''Will set the hidden value and replace the property with stars'''
    if getattr(obj, prop) != '**********':
        setattr(obj, prop+'_hidden', getattr(obj, prop))
        setattr(obj, prop, '**********')

def passAlphanumString(val):
    '''Generates random string from letters and digits'''
    allowed = string.ascii_letters + string.digits
    return ''.join([l for l in val if l in allowed])

def genRandomString(num = 6):
    '''Removing all the bad chars from the string and leaving only alphanum chars'''
    return ''.join([random.choice(string.ascii_letters + string.digits) for n in range(num)])

def genPassword(obj, prop, num = 64):
    '''Generates password and set it to property'''
    if getattr(obj, prop) != '':
        return

    setattr(obj, prop, genRandomString(num))

def genSID(obj, prop, num = 6):
    '''Generates SID and set it to property'''
    val = getattr(obj, prop)
    newval = ''
    if val == '':
        newval = genRandomString(num).lower()
    else:
        newval = passAlphanumString(val).lower()

    if newval != val:
        setattr(obj, prop, newval)

def getConfig():
    '''Function to update config when params is changed'''
    prefs = bpy.context.preferences.addons[__package__.split('.', 1)[0]].preferences

    cfg = {} # TODO: Move to ManagerConfig
    cfg['session_id'] = prefs.session_id
    cfg['dist_url'] = prefs.blender_dist_url
    cfg['dist_checksum'] = prefs.blender_dist_checksum
    if prefs.resource_provider != 'local':
        cfg['bucket'] = providers.getBucketName(cfg['session_id'])

    cfg['listen_port'] = prefs.manager_port
    cfg['auth_user'] = prefs.manager_user
    cfg['auth_password'] = prefs.manager_password_hidden
    cfg['instance_name'] = providers.getManagerName(cfg['session_id'])
    if prefs.resource_provider != 'local':
        cfg['instance_type'] = prefs.manager_instance_type

    cfg['agents_max'] = prefs.manager_agents_max
    if prefs.resource_provider != 'local':
        cfg['agent_instance_type'] = prefs.manager_agent_instance_type
        cfg['agent_use_cheap_instance'] = prefs.agent_use_cheap_instance
    cfg['agent_listen_port'] = prefs.agent_port
    cfg['agent_auth_user'] = prefs.agent_user
    cfg['agent_auth_password'] = prefs.agent_password_hidden
    cfg['agent_instance_prefix'] = providers.getAgentNamePrefix(cfg['session_id'])

    return cfg

def naturalSort(lst):
    import re
    def atoi(text):
        return int(text) if text.isdigit() else text

    def naturalKeys(text):
        return [ atoi(c) for c in re.split(r'(\d+)', text) ]

    return sorted(lst, key=naturalKeys)

def _runBackgroundWork(function, *args, **kwargs):
    '''Function to run background tasks and allow UI to continue to work'''
    thread = threading.Thread(target=function, args=args, kwargs=kwargs)
    thread.daemon = True
    thread.start()

def getProvidersEnumItems():
    '''Return the available providers list of tuples with ident, name and description for enumproperty items'''
    docs = providers.getProvidersDoc()
    return [(i, d[0], d[1]) for i, d in docs.items()]

def getProviderDocs(provider):
    '''Return the available providers list of tuples with ident, name and description for enumproperty items'''
    docs = providers.getProvidersDoc()
    return docs.get(provider, (provider, 'No documentation provided'))[1]

def getAddonDefaultProvider():
    '''Will find the first available provider for addon and return its name'''
    return providers.getGoodProvidersList()[0]

def checkProviderIsGood(provider):
    '''Make sure current choosen provider is good enough'''
    return provider in providers.getGoodProvidersList()


provider_info_cache = [{}, '', 0]

def getProviderInfo(context = None):
    '''Cached provider info for the UI interface'''
    # TODO: Not multithread for now - need to add locks

    def worker(provider, area):
        global provider_info_cache
        result = providers.getProviderInfo()
        if provider_info_cache[1] == provider:
            provider_info_cache[0] = result
        if area:
            area.tag_redraw()

    global provider_info_cache
    info = provider_info_cache
    if info[1] != getProvider() or int(time.time())-30 > info[2]:
        provider_info_cache[1] = getProvider()
        provider_info_cache[2] = time.time()
        _runBackgroundWork(worker, getProvider(), context.area if context else None)

    return info[0]


available_instance_types_cache = [[], '']
available_instance_types_mem_cache = [{}]

def fillAvailableInstanceTypes(scene, context):
    '''Cached agent available types list for the UI interface'''
    # TODO: Not multithread for now - need to add locks

    def worker(provider, area):
        global available_instance_types_cache
        result = providers.getInstanceTypes()

        if available_instance_types_cache[1] == provider:
            keys = naturalSort(result.keys())
            out = []
            out_mem = {}
            for key in keys:
                out.append( (key, key, result[key][0]) )
                out_mem[key] = result[key][1]
            available_instance_types_cache[0] = out
            available_instance_types_mem_cache[0] = out_mem
        if area:
            area.tag_redraw()

    global available_instance_types_cache
    cache = available_instance_types_cache
    if cache[1] != getProvider():
        available_instance_types_cache[1] = getProvider()
        _runBackgroundWork(worker, getProvider(), context.area)

    return cache[0]

def fillAvailableInstanceTypesManager(scene, context):
    '''Prepend available list with default key for manager'''
    default = getManagerSizeDefault()
    return [(default, default, 'default')] + fillAvailableInstanceTypes(scene, context)

def fillAvailableInstanceTypesAgent(scene, context):
    '''Prepend available list with default key for agent'''
    default = getAgentSizeDefault()
    return [(default, default, 'default')] + fillAvailableInstanceTypes(scene, context)


resources_list_cache = [{}, '', 0]

def getResources(context = None):
    '''Cached provider allocated resources'''
    # TODO: Not multithread for now - need to add locks

    def worker(provider, area):
        global resources_list_cache

        # Switch to getting the resources from the Manager if it's active
        result = {}
        if isManagerActive():
            result = ManagerClient(getManagerIP(), getConfig()).resources()
        else:
            result = providers.getResources(getConfig()['session_id'])

        if resources_list_cache[1] == provider:
            resources_list_cache[0] = result
        if area:
            area.tag_redraw()

    global resources_list_cache
    info = resources_list_cache
    if info[1] != getProvider() or int(time.time())-10 > info[2]:
        resources_list_cache[1] = getProvider()
        resources_list_cache[2] = time.time()
        _runBackgroundWork(worker, getProvider(), context.area if context else None)

    return info[0]

def getNodeLog(instance_id, context = None):
    return providers.getNodeLog(instance_id)

def getManagerIP(context = None):
    return getResources(context).get('manager', {}).get('ip')

def getManagerStatus():
    if isManagerStarted():
        return 'Active' if isManagerActive() else 'Started'
    elif isManagerStopped():
        return 'Stopped'
    else:
        return 'Unavailable'

def getStartedAgentsNumber(context = None):
    res = getResources(context)
    return len( [a for a in res.get('agents', {}).values() if a.get('started') ])

def getManagerSizeDefault():
    return providers.getManagerSizeDefault()

def getAgentSizeDefault():
    return providers.getAgentSizeDefault()


def isManagerCreated():
    return 'manager' in getResources()

def isManagerStarted():
    return getResources().get('manager', {}).get('started', False)

def isManagerStopped():
    return getResources().get('manager', {}).get('stopped', False)

def isManagerActive():
    return bool(requestManagerInfo())

def getTaskProjectPrefix():
    '''Return task-useful name based on the project name'''
    fname = bpy.path.basename(bpy.data.filepath)
    return passAlphanumString(fname[:-6]) + '-'

manager_tasks_cache = {}

def updateManagerTasks():
    '''Update cache and return the current manager tasks'''
    global manager_tasks_cache

    tasks_prop = bpy.context.window_manager.blendnet.manager_tasks

    tasks = ManagerClient(getManagerIP(), getConfig()).tasks()

    if not tasks:
        tasks_prop.clear()
        manager_tasks_cache = {}
        return

    fresh_tasks_ids = set(tasks.keys())
    cached_tasks_ids = set( task.name for task in tasks_prop )

    to_add = fresh_tasks_ids.difference(cached_tasks_ids)
    to_rem = cached_tasks_ids.difference(fresh_tasks_ids)
    for name in to_add:
        item = tasks_prop.add()
        item.name = tasks[name].get('name')

    to_download = {}
    for i, item in enumerate(tasks_prop):
        task_name = item.name
        if task_name in to_rem:
            tasks_prop.remove(i)
            continue

        task = tasks.get(task_name)
        if not task:
            continue
        if manager_tasks_cache.get(task_name) != task:
            item.create_time = str(task.get('create_time'))
            item.start_time = str(task.get('start_time'))
            item.end_time = str(task.get('end_time'))
            item.state = task.get('state')
            done = task.get('done')
            item.done = ('%.2f%%' % (done*100)) if done > 0.01 else ''

        if task_name.startswith(getTaskProjectPrefix()) and task.get('state') == 'COMPLETED':
            # Download only latest tasks frames, we don't need old ones here
            key = str(task.get('frame'))
            if key not in to_download:
                to_download[key] = item
            if to_download[key].create_time < item.create_time:
                # Mark the previous as skipped
                to_download[key].received = 'skipped'
                to_download[key] = item
            elif to_download[key].create_time > item.create_time:
                item.received = 'skipped'

    for item in to_download.values():
        if item.received:
            continue
        result = managerDownloadTaskResult(task_name, 'compose')
        if not result:
            print('INFO: Downloading the final render for %s...' % task_name)
            item.received = 'Downloading...'
        else:
            item.received = result

    manager_tasks_cache = tasks

manager_info_timer = None # Periodic timer to check the manager info
manager_info_cache = [{}, 0]

def getManagerInfo():
    '''Update cache and return the current manager info'''
    # TODO: Not multithread for now - need to add locks
    global manager_info_cache, manager_info_timer

    if manager_info_timer:
        manager_info_timer.cancel()

    print('DEBUG: Periodic update manager info')
    info = ManagerClient(getManagerIP(), getConfig()).info()
    manager_info_cache[0] = info or {}
    manager_info_cache[1] = int(time.time())

    if info:
        # Update tasks if info is here
        updateManagerTasks()

    manager_info_timer = threading.Timer(5.0, getManagerInfo)
    manager_info_timer.start()

    return manager_info_cache[0]

def requestManagerInfo(context = None):
    '''Cached request to Manager API info'''

    def worker(callback):
        getManagerInfo()

        if callback:
            callback()

    global manager_info_cache
    info = manager_info_cache
    if int(time.time())-10 > info[1]:
        manager_info_cache[1] = int(time.time())
        callback = context.area.tag_redraw if context and context.area else None
        _runBackgroundWork(worker, callback)

    return info[0]

def startManager(cfg = None):
    cfg = cfg if cfg else getConfig()
    if cfg['agent_use_cheap_instance']:
        # Calculate the agent max price according the current params
        price = getAgentPrice(cfg['agent_instance_type'])
        cfg['agent_instance_max_price'] = price[0]
        if cfg['agent_instance_max_price'] < 0.0:
            print('ERROR: Unable to run Manager - unable to determine price of agent: ' + price[1])
            return

    if not isManagerStarted():
        print('DEBUG: Running uploading to bucket')
        providers.setupBucket(cfg['bucket'], cfg)

    if not isManagerCreated():
        print('DEBUG: Creating the required firewall rules')
        providers.createFirewall('blendnet-manager', cfg['listen_port'])
        providers.createFirewall('blendnet-agent', cfg['agent_listen_port'])
        print('DEBUG: Creating manager instance')
        providers.createInstanceManager(cfg)
        # TODO: Setup subnetwork to use internal google services
    elif isManagerStopped():
        print('DEBUG: Starting manager instance')
        providers.startInstance(getResources()['manager']['id'])

def stopManager(cfg = None):
    cfg = cfg if cfg else getConfig()

    if isManagerStarted():
        print('DEBUG: Stopping manager instance')
        providers.stopInstance(getResources()['manager']['id'])

def destroyManager(cfg = None):
    def worker():
        if isManagerStopped():
            print('DEBUG: Destroying manager instance')
            providers.deleteInstance(getResources()['manager']['id'])

    _runBackgroundWork(worker)

def destroyAgent(agent_name):
    def worker():
        print('DEBUG: Destroying agent instance ' + agent_name)
        providers.deleteInstance(getResources()['agents'][agent_name]['id'])

    _runBackgroundWork(worker)

def toggleManager():
    '''Running the manager instance if it's not already started or stopping it'''
    def worker(cfg):
        if not isManagerCreated() or isManagerStopped():
            startManager(cfg)
        elif isManagerStarted():
            stopManager(cfg)

    _runBackgroundWork(worker, getConfig())

manager_task_upload_workers = None

def _managerTaskUploadFilesWorker(task, rel_path, file_path):
    '''Gets item and uploads using client'''
    while True:
        ret = ManagerClient(getManagerIP(), getConfig()).taskFilePut(task, file_path, rel_path)
        if ret:
            break
        print('WARN: Uploading of "%s" to task "%s" failed, repeating...' % (rel_path, task))
        time.sleep(1.0)
    print('DEBUG: Uploading of "%s" to task "%s" completed' % (rel_path, task))

def managerTaskUploadFiles(task, files_map):
    '''Multithreading task files upload'''

    if managerTaskUploadFilesStatus():
        print('ERROR: Upload files already in progress...')
        return

    global manager_task_upload_workers
    if manager_task_upload_workers is None:
        manager_task_upload_workers = Workers(
            'Uploading tasks files to Manager',
            8,
            _managerTaskUploadFilesWorker,
        )

    manager_task_upload_workers.addSet(set( (task, rel, path) for rel, path in files_map.items() ))

def managerTaskUploadFilesStatus():
    '''Returns string to show user about the status of uploading'''
    global manager_task_upload_workers
    if manager_task_upload_workers and manager_task_upload_workers.tasksLeft() > 0:
        return '%d left to upload...' % manager_task_upload_workers.tasksLeft()
    return None

manager_task_download_workers = None

def _managerDownloadTaskResultsWorker(task, result, file_path):
    '''Gets item and downloads using client'''
    ret = None
    for repeat in range(0, 3):
        ret = managerTaskResultDownload(task, result, file_path)
        if ret:
            break
        print('WARN: Downloading of "%s" from task "%s" into "%s" failed, repeating (%s)...' % (
            result, task, file_path, repeat
        ))
        time.sleep(1.0)
    if ret:
        print('DEBUG: Downloading of "%s" from task "%s" into "%s" completed' % (result, task, file_path))
    else:
        print('ERROR: Download error: %s' % (ret,))
    # Set the downloaded file path to the item received field
    for item in bpy.context.window_manager.blendnet.manager_tasks:
        if item.name == task and result == 'compose' and item.received != 'skipped':
            item.received = file_path

def managerDownloadTaskResult(task_name, result_to_download, tempdir = None):
    '''Check the result existance and download if it's not matching the existing one'''
    out_dir = os.path.dirname(bpy.path.abspath(bpy.context.scene.render.filepath))
    out_path = os.path.join(out_dir, result_to_download, task_name + '.exr')
    if result_to_download == 'compose':
        compose_filepath = managerTaskStatus(task_name).get('compose_filepath')
        out_path = bpy.path.abspath(compose_filepath)
    if not os.path.isabs(out_path):
        out_path = os.path.abspath(out_path)
    if tempdir:
        # Download to temp folder just to preview the task result
        out_path = os.path.join(tempdir, task_name + os.path.splitext(out_path)[-1])

    result = True
    checksum = None
    # Check the local file first - maybe it's the thing we need
    if os.path.isfile(out_path):
        # Calculate sha1 to make sure it's the same file
        sha1_calc = hashlib.sha1()
        with open(out_path, 'rb') as f:
            for chunk in iter(lambda: f.read(1048576), b''):
                sha1_calc.update(chunk)
        checksum = sha1_calc.hexdigest()
        # If file and checksum are here - we need to get the actual task status to compare
        result = managerTaskStatus(task_name).get('result', {}).get(result_to_download)

    # If file is not working for us - than download
    if checksum != result:
        global manager_task_download_workers
        if manager_task_download_workers is None:
            manager_task_download_workers = Workers(
                'Downloading files from Manager',
                8,
                _managerDownloadTaskResultsWorker,
            )

        manager_task_download_workers.add(task_name, result_to_download, out_path)
        manager_task_download_workers.start()
        return None
    return out_path

def managerTaskConfig(task, conf):
    return ManagerClient(getManagerIP(), getConfig()).taskConfigPut(task, conf)

def managerTaskRun(task):
    return ManagerClient(getManagerIP(), getConfig()).taskRun(task)

def managerTaskStatus(task):
    return ManagerClient(getManagerIP(), getConfig()).taskStatus(task)

def managerTaskMessages(task):
    return ManagerClient(getManagerIP(), getConfig()).taskMessages(task)

def managerTaskDetails(task):
    return ManagerClient(getManagerIP(), getConfig()).taskDetails(task)

def managerTaskStop(task):
    return ManagerClient(getManagerIP(), getConfig()).taskStop(task)

def managerTaskRemove(task):
    return ManagerClient(getManagerIP(), getConfig()).taskRemove(task)

def managerTaskResultDownload(task, result, file_path):
    return ManagerClient(getManagerIP(), getConfig()).taskResultDownload(task, result, file_path)

def managerAgentCreate(agent_name, conf):
    return ManagerClient(getManagerIP(), getConfig()).agentCreate(agent_name, conf)

def managerAgentRemove(agent_name):
    return ManagerClient(getManagerIP(), getConfig()).agentRemove(agent_name)

def managerGetLog():
    return ManagerClient(getManagerIP(), getConfig()).log()

def agentGetLog(agent_name):
    return ManagerClient(getManagerIP(), getConfig()).agentLog(agent_name)


available_blender_dists_cache = None
available_blender_dists_cache_list = []

def fillAvailableBlenderDists(scene = None, context = None):
    '''Cached blender dists list for the UI interface'''
    # TODO: Not multithread for now - need to add locks

    def worker(area):
        global available_blender_dists_cache
        global available_blender_dists_cache_list

        mirrors = [
            'https://download.blender.org/release/',
            'https://mirror.clarkson.edu/blender/release/',
            'https://ftp.nluug.nl/pub/graphics/blender/release/',
        ]

        ctx = ssl.create_default_context()
        print('INFO: Search for blender embedded certificates...')
        for path in site.getsitepackages():
            path = os.path.join(path, 'certifi', 'cacert.pem')
            if not os.path.exists(path):
                continue
            ctx.load_verify_locations(cafile=path)
            print('INFO: found certifi certificates: %s' % (path,))
            break

        if len(ctx.get_ca_certs()) == 0:
            print('WARN: certificates not found - skip certs verification')
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        for url in mirrors:
            try:
                # Getting the first layer of mirror list
                parser = LinkHTMLParser()
                with urlopen(url, timeout=5, context=ctx) as f:
                    parser.feed(f.read().decode())

                # Processing links of the first layer
                links = parser.links()
                dirs = []
                for l in links:
                    if not l.startswith('Blender'):
                        continue
                    ver = int(''.join(c for c in l if c.isdigit()))
                    if ver >= 280: # >= 2.80 is supported
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
                                available_blender_dists_cache[ver] = {
                                    'url': url+d+name,
                                    'checksum': sha256,
                                }
                                print('INFO: found blender version: %s (%s %s)' % (ver, url, sha256))

                # Don't need to check the other sites
                break

            except Exception as e:
                print('WARN: unable to get mirror list for: %s %s' % (url, e))

        keys = naturalSort(available_blender_dists_cache.keys())
        out = []
        for key in keys:
            out.append( (key, key, available_blender_dists_cache[key]['url']) )
        available_blender_dists_cache_list = out

        updateBlenderDistProp()

        if area:
            area.tag_redraw()

    global available_blender_dists_cache
    global available_blender_dists_cache_list
    if available_blender_dists_cache is None:
        available_blender_dists_cache = {}
        _runBackgroundWork(worker, context.area if context else None)
        return available_blender_dists_cache_list

    return available_blender_dists_cache_list

def updateBlenderDistProp(version = None):
    '''Update the dist property if not set to custom'''
    prefs = bpy.context.preferences.addons[__package__.split('.', 1)[0]].preferences
    if prefs.blender_dist_custom:
        return

    client_version = bpy.app.version_string.split()[0]
    if not version:
        version = client_version
    elif version != client_version and not prefs.blender_dist_custom:
        # If user changing it - than it's become custom
        prefs.blender_dist_custom = True

    if version not in available_blender_dists_cache:
        print('WARN: unable to find blender dist version, using the closest one for', version)
        import difflib
        vers = difflib.get_close_matches(version, available_blender_dists_cache.keys(), cutoff=0.0)
        if len(vers):
            version = vers[0]
            print('WARN: choosen:', version)
        else:
            version = available_blender_dists_cache.keys()[-1]
            print('WARN: Unable to find the good one, use latest:', version)

    if prefs.blender_dist != version:
        prefs.blender_dist = version
    prefs.blender_dist_url = available_blender_dists_cache[version]['url']
    prefs.blender_dist_checksum = available_blender_dists_cache[version]['checksum']

def checkAgentMemIsEnough():
    '''Making sure the current agent type have enough memory to render the scene'''
    bn = bpy.context.scene.blendnet
    prefs = bpy.context.preferences.addons[__package__.split('.', 1)[0]].preferences
    if prefs.resource_provider == 'local':
        return True # TODO: no good way to get it done for now
    return available_instance_types_mem_cache[0].get(prefs.manager_agent_instance_type, 0) >= bn.scene_memory_req


def getCheapMultiplierList(scene = None, context = None):
    l = providers.getCheapMultiplierList()
    return [ (str(v),str(v),str(v)) for v in l ]


instance_type_price_manager_cache = [(0.0, 'LOADING...'), '']

def getManagerPrice(inst_type):
    global instance_type_price_manager_cache

    instance_type_price_manager_cache[0] = providers.getPrice(inst_type, 1.0)

    return instance_type_price_manager_cache[0]

def getManagerPriceBG(inst_type, context = None):
    def worker(callback):
        getManagerPrice(inst_type)

        if callback:
            callback()

    global instance_type_price_manager_cache
    info = instance_type_price_manager_cache
    if info[1] != inst_type:
        instance_type_price_manager_cache[1] = inst_type
        callback = context.area.tag_redraw if context and context.area else None
        _runBackgroundWork(worker, callback)

    return info[0]


instance_type_price_agent_cache = [(0.0, 'LOADING...'), '', None, -1.0]

def getAgentPrice(inst_type):
    global instance_type_price_agent_cache

    cheap_multiplier = 1.0
    prefs = bpy.context.preferences.addons[__package__.split('.', 2)[0]].preferences
    if prefs.agent_use_cheap_instance and prefs.agent_cheap_multiplier != '':
        cheap_multiplier = float(prefs.agent_cheap_multiplier)
    instance_type_price_agent_cache[0] = providers.getPrice(inst_type, cheap_multiplier)

    return instance_type_price_agent_cache[0]

def getAgentPriceBG(inst_type, context = None):
    def worker(callback):
        getAgentPrice(inst_type)

        if callback:
            callback()

    global instance_type_price_agent_cache
    info = instance_type_price_agent_cache
    prefs = bpy.context.preferences.addons[__package__.split('.', 1)[0]].preferences
    if info[1] != inst_type or info[2] != prefs.agent_use_cheap_instance and info[3] != prefs.agent_cheap_multiplier:
        instance_type_price_agent_cache[1] = inst_type
        instance_type_price_agent_cache[2] = prefs.agent_use_cheap_instance
        instance_type_price_agent_cache[3] = prefs.agent_cheap_multiplier
        callback = context.area.tag_redraw if context and context.area else None
        _runBackgroundWork(worker, callback)

    return info[0]


instance_type_price_minimal_cache = [-1.0, '', 0]

def getMinimalCheapPrice(inst_type):
    global instance_type_price_minimal_cache
    instance_type_price_minimal_cache[0] = providers.getMinimalCheapPrice(inst_type)

    return instance_type_price_minimal_cache[0]

def getMinimalCheapPriceBG(inst_type, context = None):
    def worker(callback):
        getMinimalCheapPrice(inst_type)

        if callback:
            callback()

    global instance_type_price_minimal_cache
    info = instance_type_price_minimal_cache
    if info[1] != inst_type or time.time() > info[2]:
        instance_type_price_minimal_cache[1] = inst_type
        instance_type_price_minimal_cache[2] = time.time() + 600
        callback = context.area.tag_redraw if context and context.area else None
        _runBackgroundWork(worker, callback)

    return info[0]

def showLogWindow(prefix, data):
    '''Opens a new window and shows the log in it'''
    log_file = tempfile.NamedTemporaryFile(mode='w', encoding='UTF-8',
            prefix=prefix + '_' + datetime.now().strftime('%y%m%d-%H%M%S_'),
            suffix='.log')
    log_file.write(data)
    log_file.flush()

    bpy.ops.text.open(filepath=log_file.name, internal=True)

    # Opening new window to show the log
    bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
    area = bpy.context.window_manager.windows[-1].screen.areas[0]
    if area.type == 'PREFERENCES':
        area.type = 'TEXT_EDITOR'
        area.spaces[0].show_line_numbers = False
        area.spaces[0].show_syntax_highlight = False
        area.spaces[0].text = bpy.data.texts[os.path.basename(log_file.name)]
        return True
    return False
