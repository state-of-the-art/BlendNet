#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''Blender Addon UI functions
'''

import time
import threading

from . import providers
from . import ManagerClient
from .Workers import Workers

def selectProvider(provider):
    '''Sets the current provider identifier'''
    print('DEBUG: selected provider: %s' % provider)
    providers.selectProvider(provider)

def getProvider():
    '''Returns the current provider identifier'''
    return providers.selected_provider

def hidePassword(obj, prop):
    '''Will set the hidden value and replace the property with stars'''
    setattr(obj, prop+'_hidden', getattr(obj, prop))
    setattr(obj, prop, '**********')

def passAlphanumString(val):
    '''Generates random string from letters and digits'''
    import string
    allowed = string.ascii_letters + string.digits
    return ''.join([l for l in val if l in allowed])

def genRandomString(num = 6):
    '''Removing all the bad chars from the string and leaving only alphanum chars'''
    import random, string
    return ''.join([random.choice(string.ascii_letters + string.digits) for n in range(num)])

def genPassword(obj, prop, num = 64):
    '''Generates password and set it to property'''
    if getattr(obj, prop) != '':
        return

    setattr(obj, prop, genRandomString(num))

def genSID(obj, prop, num = 6):
    '''Generates SID and set it to property'''

    import random, string
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
    import bpy
    prefs = bpy.context.preferences.addons[__package__.split('.', 1)[0]].preferences
    bn = bpy.context.scene.blendnet

    cfg = {} # TODO: Move to ManagerConfig
    cfg['session_id'] = prefs.session_id
    cfg['bucket'] = providers.getBucketName(cfg['session_id'])

    cfg['listen_port'] = prefs.manager_port
    cfg['auth_user'] = prefs.manager_user
    cfg['auth_password'] = prefs.manager_password_hidden
    cfg['instance_name'] = providers.getManagerName(cfg['session_id'])
    cfg['instance_type'] = bn.manager_instance_type

    cfg['agents_max'] = bn.manager_agents_max
    cfg['agent_instance_type'] = bn.manager_agent_instance_type
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

def getAddonDefaultProvider():
    '''Will find the first available provider for addon and return its name'''
    return providers.getGoodProvidersList()[0]


provider_info_cache = [{}, '', 0]

def getProviderInfo(context):
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
        _runBackgroundWork(worker, getProvider(), context.area)

    return info[0]


available_instance_types_cache = [[], '']

def fillAvailableInstanceTypes(scene, context):
    '''Cached agent available types list for the UI interface'''
    # TODO: Not multithread for now - need to add locks

    def worker(provider, area):
        global available_instance_types_cache
        result = providers.getInstanceTypes()

        if available_instance_types_cache[1] == provider:
            keys = naturalSort(result.keys())
            out = []
            for key in keys:
                out.append( (key, key, result[key]) )
            available_instance_types_cache[0] = out
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

def getManagerIP(context = None):
    res = getResources(context)
    return res.get('manager', {}).get('ip')

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

manager_tasks_cache = {}

def updateManagerTasks():
    '''Update cache and return the current manager tasks'''
    import bpy
    global manager_tasks_cache

    tasks_prop = bpy.context.window_manager.blendnet.manager_tasks

    tasks = ManagerClient(getManagerIP(), getConfig()).tasks()

    if not tasks:
        tasks_prop.clear()
        manager_tasks_cache = {}
        return

    fresh_tasks_ids = set(tasks.keys())
    cached_tasks_ids = set(manager_tasks_cache.keys())

    to_add = fresh_tasks_ids.difference(cached_tasks_ids)
    to_rem = cached_tasks_ids.difference(fresh_tasks_ids)
    for name in to_add:
        item = tasks_prop.add()
        item.name = tasks[name].get('name')
    for i, item in enumerate(tasks_prop):
        name = item.name
        if name in to_rem:
            tasks_prop.remove(i)
            continue
        if manager_tasks_cache.get(name) != tasks.get(name):
            item.create_time = str(tasks[name].get('create_time'))
            item.start_time = str(tasks[name].get('start_time'))
            item.end_time = str(tasks[name].get('end_time'))
            item.state = tasks[name].get('state')
            done = tasks[name].get('done')
            item.done = ('%.2f%%' % (done*100)) if done > 0.01 else None

    manager_tasks_cache = tasks

manager_info_timer = None # Periodic timer to check the manager info
manager_info_cache = [{}, 0]

def getManagerInfo():
    '''Update cache and return the current manager info'''
    # TODO: Not multithread for now - need to add locks
    global manager_info_cache, manager_info_timer

    if manager_info_timer:
        manager_info_timer.cancel()

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

    if not isManagerStarted():
        print('DEBUG: Running uploading to bucket')
        providers.setupBucket(cfg['bucket'], cfg)

    if not isManagerCreated():
        print('DEBUG: Creating manager instance')
        providers.createInstanceManager(cfg['instance_type'], cfg['session_id'], cfg['instance_name'])
        print('DEBUG: Creating the required firewall rules')
        providers.createFirewall('blendnet-manager', cfg['listen_port'])
        # Not needed firewall for agent - manager is using internal agent ip
        #providers.createFirewall('blendnet-agent', cfg['agent_listen_port'])
        # TODO: Setup subnetwork to use internal google services
    elif isManagerStopped():
        print('DEBUG: Starting manager instance')
        providers.startInstance(cfg['instance_name'])

def stopManager(cfg = None):
    cfg = cfg if cfg else getConfig()

    if isManagerStarted():
        print('DEBUG: Stopping manager instance')
        providers.stopInstance(cfg['instance_name'])

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
    if manager_task_upload_workers == None:
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
