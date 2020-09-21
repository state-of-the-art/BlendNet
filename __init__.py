bl_info = {
    'name': 'BlendNet - distributed cloud render',
    'author': 'www.state-of-the-art.io',
    'version': (0, 4, 0),
    'warning': 'development version',
    'blender': (2, 80, 0),
    'location': 'Properties --> Render --> BlendNet Render',
    'description': 'Allows to easy allocate resources in cloud and '
                   'run the cycles rendering with getting preview '
                   'and results',
    'wiki_url': 'https://github.com/state-of-the-art/BlendNet/wiki',
    'tracker_url': 'https://github.com/state-of-the-art/BlendNet/issues',
    'category': 'Render',
}

if 'bpy' in locals():
    import importlib
    importlib.reload(BlendNet)
    importlib.reload(blend_file)
else:
    from . import (
        BlendNet,
    )
    from .BlendNet import blend_file

import os
import time
import tempfile
from datetime import datetime

import bpy
from bpy.props import (
    BoolProperty,
    IntProperty,
    StringProperty,
    EnumProperty,
    PointerProperty,
    CollectionProperty,
)

class BlendNetAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    resource_provider: EnumProperty(
        name = 'Provider',
        description = 'Engine to provide resources for rendering',
        items = BlendNet.addon.getProvidersEnumItems(),
        update = lambda self, context: BlendNet.addon.selectProvider(self.resource_provider),
    )

    # Advanced
    blender_dist: EnumProperty(
        name = 'Blender dist',
        description = 'Blender distributive to use on manager/agents. '
            'By default it\'s set to the current blender version and if '
            'you want to change it - you will deal with the custom URL',
        items = BlendNet.addon.fillAvailableBlenderDists,
        update = lambda self, context: BlendNet.addon.updateBlenderDistProp(self.blender_dist),
    )

    blender_dist_url: StringProperty(
        name = 'Blender dist URL',
        description = 'URL to download the blender distributive',
        default = '',
    )

    blender_dist_checksum: StringProperty(
        name = 'Blender dist checksum',
        description = 'Checksum of the distributive to validate the binary',
        default = '',
    )

    blender_dist_custom: BoolProperty(
        name = 'Custom dist URL',
        description = 'Use custom url instead the automatic one',
        default = False,
        update = lambda self, context: BlendNet.addon.updateBlenderDistProp(),
    )

    session_id: StringProperty(
        name = 'Session ID',
        description = 'Identifier of the session and allocated resources. '
                      'It is used to properly find your resources in the GCP '
                      'project and separate your resources from the other ones. '
                      'Warning: Please be careful with this option and don\'t '
                      'change it if you don\'t know what it\'s doing',
        maxlen = 12,
        update = lambda self, context: BlendNet.addon.genSID(self, 'session_id'),
    )

    manager_instance_type: EnumProperty(
        name = 'Manager size',
        description = 'Selected manager instance size',
        items = BlendNet.addon.fillAvailableInstanceTypesManager,
    )

    manager_ca_path: StringProperty(
        name = 'CA certificate',
        description = 'Certificate Authority certificate pem file location',
        subtype = 'FILE_PATH',
        default = '',
    )

    manager_address: StringProperty(
        name = 'Address',
        description = 'If you using the existing Manager service put address here '
                      '(it will be automatically created otherwise)',
        default = '',
    )

    manager_port: IntProperty(
        name = 'Port',
        description = 'TLS tcp port to communicate Addon with Manager service',
        min = 1,
        max = 65535,
        default = 8443,
    )

    manager_user: StringProperty(
        name = 'User',
        description = 'HTTP Basic Auth username (will be generated if empty)',
        maxlen = 32,
        default = 'blendnet-manager',
    )

    manager_password: StringProperty(
        name = 'Password',
        description = 'HTTP Basic Auth password (will be generated if empty)',
        subtype = 'PASSWORD',
        maxlen = 128,
        default = '',
        update = lambda self, context: BlendNet.addon.hidePassword(self, 'manager_password'),
    )

    manager_agent_instance_type: EnumProperty(
        name = 'Agent size',
        description = 'Selected agent instance size',
        items = BlendNet.addon.fillAvailableInstanceTypesAgent,
    )

    manager_agents_max: IntProperty(
        name = 'Agents max',
        description = 'Maximum number of agents in Manager\'s pool',
        min = 1,
        max = 65535,
        default = 3,
    )

    agent_use_cheap_instance: BoolProperty(
        name = 'Use cheap VM',
        description = 'Use cheap instances to save money',
        default = True,
    )

    agent_cheap_multiplier: EnumProperty(
        name = 'Cheap multiplier',
        description = 'Way to choose the price to get a cheap VM. '
            'Some providers allows to choose the maximum price for the instance '
            'and it could be calculated from the ondemand (max) price multiplied by this value.',
        items = BlendNet.addon.getCheapMultiplierList,
    )

    agent_port: IntProperty(
        name = 'Port',
        description = 'TLS tcp port to communicate Manager with Agent service',
        min = 1,
        max = 65535,
        default = 9443,
    )

    agent_user: StringProperty(
        name = 'User',
        description = 'HTTP Basic Auth username (will be generated if empty)',
        maxlen = 32,
        default = 'blendnet-agent',
    )

    agent_password: StringProperty(
        name = 'Password',
        description = 'HTTP Basic Auth password (will be generated if empty)',
        subtype = 'PASSWORD',
        maxlen = 128,
        default = '',
        update = lambda self, context: BlendNet.addon.hidePassword(self, 'agent_password'),
    )

    # Hidden
    show_advanced: BoolProperty(
        name = 'Advanced Properties',
        description = 'Show/Hide the advanced properties',
        default = False,
    )

    manager_password_hidden: StringProperty(
        subtype = 'PASSWORD',
        update = lambda self, context: BlendNet.addon.genPassword(self, 'manager_password_hidden'),
    )

    agent_password_hidden: StringProperty(
        subtype = 'PASSWORD',
        update = lambda self, context: BlendNet.addon.genPassword(self, 'agent_password_hidden'),
    )

    def draw(self, context):
        layout = self.layout

        # Provider
        box = layout.box()
        split = box.split(factor=0.8)
        split.prop(self, 'resource_provider')
        info = BlendNet.addon.getProviderDocs(self.resource_provider).split('\n')
        for line in info:
            if line.startswith('Help: '):
                split.operator('wm.url_open', text='How to setup', icon='HELP').url = line.split(': ', 1)[-1]
        if not BlendNet.addon.checkProviderIsGood(self.resource_provider):
            err = BlendNet.addon.getProviderDocs(self.resource_provider).split('\n')
            for line in err:
                box.label(text=line.strip(), icon='ERROR')
        if self.resource_provider != 'local':
            box = box.box()
            box.label(text='Collected cloud info:')

            provider_info = BlendNet.addon.getProviderInfo(context)
            if 'ERRORS' in provider_info:
                for err in provider_info['ERRORS']:
                    box.label(text=err, icon='ERROR')

            for key, value in provider_info.items():
                if key == 'ERRORS':
                    continue
                split = box.split(factor=0.5)
                split.label(text=key, icon='DOT')
                split.label(text=value)

        # Advanced properties panel
        advanced_icon = 'TRIA_RIGHT' if not self.show_advanced else 'TRIA_DOWN'
        box = layout.box()
        box.prop(self, 'show_advanced', emboss=False, icon=advanced_icon)

        if self.show_advanced:
            if self.resource_provider != 'local':
                row = box.row()
                row.prop(self, 'session_id')
                row = box.row(align=True)
                row.prop(self, 'blender_dist_custom', text='')
                if not self.blender_dist_custom:
                    row.prop(self, 'blender_dist')
                else:
                    row.prop(self, 'blender_dist_url')
                    box.row().prop(self, 'blender_dist_checksum')

            box_box = box.box()
            box_box.label(text='Manager')
            if self.resource_provider != 'local':
                row = box_box.row()
                row.prop(self, 'manager_instance_type', text='Type')
                row = box_box.row()
                price = BlendNet.addon.getManagerPriceBG(self.manager_instance_type, context)
                if price[0] < 0.0:
                    row.label(text='WARNING: Unable to find price for the type "%s": %s' % (
                        self.manager_instance_type, price[1]
                    ), icon='ERROR')
                else:
                    row.label(text='Calculated price: ~%s/Hour (%s)' % (round(price[0], 12), price[1]))

            if self.resource_provider == 'local':
                row = box_box.row()
                row.use_property_split = True
                row.prop(self, 'manager_address')
                row = box_box.row()
                row.use_property_split = True
                row.prop(self, 'manager_ca_path')
            row = box_box.row()
            row.use_property_split = True
            row.prop(self, 'manager_port')
            row = box_box.row()
            row.use_property_split = True
            row.prop(self, 'manager_user')
            row = box_box.row()
            row.use_property_split = True
            row.prop(self, 'manager_password')

            box_box = box.box()
            box_box.label(text='Agent')
            if self.resource_provider != 'local':
                row = box_box.row()
                row.prop(self, 'agent_use_cheap_instance')
                if 'Cheap instances not available' in provider_info.get('ERRORS', []):
                    row.enabled = False
                else:
                    row.prop(self, 'agent_cheap_multiplier')
                row = box_box.row()
                row.enabled = not BlendNet.addon.isManagerCreated()
                row.prop(self, 'manager_agent_instance_type', text='Agents type')
                row.prop(self, 'manager_agents_max', text='Agents max')
                row = box_box.row()
                price = BlendNet.addon.getAgentPriceBG(self.manager_agent_instance_type, context)
                if price[0] < 0.0:
                    row.label(text='ERROR: Unable to find price for the type "%s": %s' % (
                        self.manager_agent_instance_type, price[1]
                    ), icon='ERROR')
                else:
                    row.label(text='Calculated combined price: ~%s/Hour (%s)' % (
                        round(price[0] * self.manager_agents_max, 12), price[1]
                    ))
                min_price = BlendNet.addon.getMinimalCheapPriceBG(self.manager_agent_instance_type, context)
                if min_price > 0.0:
                    row = box_box.row()
                    row.label(text='Minimal combined price: ~%s/Hour' % (
                        round(min_price * self.manager_agents_max, 12),
                    ))
                    if price[0] <= min_price:
                        row = box_box.row()
                        row.label(text='ERROR: Selected cheap price is lower than minimal one', icon='ERROR')
            row = box_box.row()
            row.use_property_split = True
            row.prop(self, 'agent_port')
            row = box_box.row()
            row.use_property_split = True
            row.prop(self, 'agent_user')
            row = box_box.row()
            row.use_property_split = True
            row.prop(self, 'agent_password')

class BlendNetSceneSettings(bpy.types.PropertyGroup):
    scene_memory_req: IntProperty(
        name = 'Scene RAM to render',
        description = 'Required memory to render the scene in GB',
        min = 0,
        max = 65535,
        default = 0,
    )

    @classmethod
    def register(cls):
        bpy.types.Scene.blendnet = PointerProperty(
            name = 'BlendNet Settings',
            description = 'BlendNet scene settings',
            type = cls
        )

    @classmethod
    def unregister(cls):
        if hasattr(bpy.types.Scene, 'blendnet'):
            del bpy.types.Scene.blendnet

class BlendNetManagerTask(bpy.types.PropertyGroup):
    '''Class contains the manager task information'''
    name: StringProperty()
    create_time: StringProperty()
    start_time: StringProperty()
    end_time: StringProperty()
    state: StringProperty()
    done: StringProperty()
    received: StringProperty()

class BlendNetSessionProperties(bpy.types.PropertyGroup):
    original_render_engine: StringProperty(
        name = 'Original scene render engine',
        description = 'Used to temporarily store the original render engine '
                      'and restore it when the rendering is started',
        default = '',
    )

    manager_tasks: CollectionProperty(
        name = 'Manager tasks',
        description = 'Contains all the tasks that right now is available '
                      'on manager',
        type = BlendNetManagerTask,
    )
    manager_tasks_idx: IntProperty(default=0)

    status: StringProperty(
        name = 'BlendNet status',
        description = 'BlendNet is performing some operation',
        default = 'idle',
    )

    @classmethod
    def register(cls):
        bpy.types.WindowManager.blendnet = PointerProperty(
            name = 'BlendNet Session Properties',
            description = 'Just current status of process for internal use',
            type = cls,
        )

    @classmethod
    def unregister(cls):
        if hasattr(bpy.types.WindowManager, 'blendnet'):
            del bpy.types.WindowManager.blendnet

class BlendNetToggleManager(bpy.types.Operator):
    bl_idname = 'blendnet.togglemanager'
    bl_label = ''
    bl_description = 'Start/Stop manager instance'

    retry_counter: IntProperty(default=50)

    _timer = None
    _last_run = 0

    @classmethod
    def poll(cls, context):
        return context.window_manager.blendnet.status == 'idle'

    def invoke(self, context, event):
        self.retry_counter = 50
        wm = context.window_manager
        BlendNet.addon.toggleManager()

        if BlendNet.addon.isManagerStarted():
            self.report({'INFO'}, 'BlendNet stopping Manager instance...')
            wm.blendnet.status = 'Manager stopping...'
        else:
            self.report({'INFO'}, 'BlendNet starting Manager instance...')
            wm.blendnet.status = 'Manager starting...'

        if context.area:
            context.area.tag_redraw()
        wm.modal_handler_add(self)
        self._timer = wm.event_timer_add(5.0, window=context.window)

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER' or self._last_run + 4.5 > time.time():
            return {'PASS_THROUGH'}

        self._last_run = time.time()

        return self.execute(context)

    def execute(self, context):
        wm = context.window_manager

        self.retry_counter -= 1
        if self.retry_counter < 0:
            self.report({'ERROR'}, 'BlendNet Manager operation reached maximum retries - something bad happened '
                                   'on "%s" stage. Please consult the documentation' % wm.blendnet.status)
            wm.blendnet.status = 'idle'
            return {'FINISHED'}

        if wm.blendnet.status == 'Manager starting...':
            if not BlendNet.addon.isManagerStarted():
                return {'PASS_THROUGH'}
            self.report({'INFO'}, 'BlendNet Manager started')
            wm.blendnet.status = 'Manager ping...'
            if context.area:
                context.area.tag_redraw()
            BlendNet.addon.requestManagerInfo(context)
        elif wm.blendnet.status == 'Manager stopping...':
            if not BlendNet.addon.isManagerStopped():
                return {'PASS_THROUGH'}

        if wm.blendnet.status == 'Manager ping...':
            if not BlendNet.addon.requestManagerInfo(context):
                return {'PASS_THROUGH'}
            self.report({'INFO'}, 'BlendNet Manager connected')

        if self._timer is not None:
            wm.event_timer_remove(self._timer)
        wm.blendnet.status = 'idle'
        if context.area:
            context.area.tag_redraw()

        return {'FINISHED'}

class BlendNetDestroyManager(bpy.types.Operator):
    bl_idname = 'blendnet.destroymanager'
    bl_label = ''
    bl_description = 'Destroy manager instance'

    @classmethod
    def poll(cls, context):
        return BlendNet.addon.isManagerStopped()

    def invoke(self, context, event):
        BlendNet.addon.destroyManager()
        self.report({'INFO'}, 'BlendNet destroy Manager instance...')

        return {'FINISHED'}

class BlendNetTaskPreviewOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskpreview'
    bl_label = 'Open preview'
    bl_description = 'Show the render for the currently selected task'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        return len(bn.manager_tasks) > bn.manager_tasks_idx

    def _findRenderResultArea(self, context):
        for window in context.window_manager.windows:
            if window.scene != context.scene:
                continue
            for area in window.screen.areas:
                if area.type != 'IMAGE_EDITOR':
                    continue
                if area.spaces.active.image.type == 'RENDER_RESULT':
                    return area
        return None

    def invoke(self, context, event):
        # Show the preview of the render if not open
        if not self._findRenderResultArea(context):
            bpy.ops.render.view_show('INVOKE_DEFAULT')

        # Save the original render engine to run render on BlendNet
        context.window_manager.blendnet.original_render_engine = context.scene.render.engine
        context.scene.render.engine = __package__
        # Start the render process
        self.result = bpy.ops.render.render('INVOKE_DEFAULT')

        return {'FINISHED'}

class BlendNetRunTaskOperation(bpy.types.Operator):
    bl_idname = 'blendnet.runtask'
    bl_label = 'Run Task'
    bl_description = 'Run Manager task using BlendNet resources'

    is_animation: BoolProperty(
        name = 'Animation',
        description = 'Runs animation rendering instead of just a still image rendering',
        default = False
    )

    _timer = None

    _project_file: None # temp blend project file to ensure it will not be changed
    _frame: 0 # current/start frame depends on animation
    _frame_to: 0 # end frame for animation
    _frame_orig: 0 # to restore the current frame after animation processing
    _task_name: None # store task name to retry later

    @classmethod
    def poll(cls, context):
        return True

    def _findRenderResultArea(self, context):
        for window in context.window_manager.windows:
            if window.scene != context.scene:
                continue
            for area in window.screen.areas:
                if area.type != 'IMAGE_EDITOR':
                    continue
                if area.spaces.active.image.type == 'RENDER_RESULT':
                    return area

    def init(self, context):
        '''Initializes the execution'''
        if not bpy.data.filepath:
            self.report({'ERROR'}, 'Unable to render not saved project. Please save it somewhere.')
            return {'CANCELLED'}

        # Fix and verify the blendfile dependencies
        bads = blend_file.getDependencies()[1]
        if bads:
            self.report({'ERROR'}, 'Found some bad dependencies - please fix them before run: %s' % bads)
            return {'CANCELLED'}

        # Run the Manager if it's not started
        if not BlendNet.addon.isManagerCreated() or BlendNet.addon.isManagerStopped():
            if bpy.ops.blendnet.togglemanager.poll():
                bpy.ops.blendnet.togglemanager('INVOKE_DEFAULT')

        # Saving project to the same directory
        try:
            self._project_file = bpy.data.filepath + '_blendnet.blend'
            bpy.ops.wm.save_as_mainfile(
                filepath = self._project_file,
                check_existing = False,
                compress = True,
                copy = True,
            )
        except Exception as e:
            self.report({'ERROR'}, 'Unable to save the "_blendnet.blend" project file: %s' % e)
            return {'CANCELLED'}

        if self.is_animation:
            self._frame = context.scene.frame_start
            self._frame_to = context.scene.frame_end
            self._frame_orig = context.scene.frame_current
        else:
            self._frame = context.scene.frame_current

        self._task_name = None

        context.window_manager.modal_handler_add(self)
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        return self.init(context)

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Waiting for manager
        if not BlendNet.addon.isManagerActive():
            return {'PASS_THROUGH'}

        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        wait = False
        if not hasattr(self, '_frame'):
            wait = True # The execute is running directly, so run in fg
            if 'CANCELLED' in self.init(context):
                self.report({'ERROR'}, 'Unable to init task preparation')
                return {'CANCELLED'}

        scene.frame_current = self._frame

        fname = bpy.path.basename(bpy.data.filepath)
        if not self._task_name:
            # If the operation is not completed - reuse the same task name
            d = datetime.utcnow().strftime('%y%m%d%H%M')
            self._task_name = '%s%s-%d-%s' % (
                BlendNet.addon.getTaskProjectPrefix(),
                d, scene.frame_current,
                BlendNet.addon.genRandomString(3)
            )

            print('DEBUG: Uploading task "%s" to the manager' % self._task_name)

            # Prepare list of files need to be uploaded
            base_dir = os.path.dirname(bpy.path.abspath(bpy.data.filepath))
            deps, bads = blend_file.getDependencies()
            if bads:
                self.report({'ERROR'}, 'Found some bad dependencies - please fix them before run: %s' % bads)
                return {'CANCELLED'}

            deps_map = dict([ (rel, os.path.join(base_dir, rel)) for rel in deps ])
            deps_map[fname] = self._project_file

            # Run the dependencies upload background process
            BlendNet.addon.managerTaskUploadFiles(self._task_name, deps_map)

            # Slow down the check process
            if self._timer is not None:
                context.window_manager.event_timer_remove(self._timer)
            self._timer = context.window_manager.event_timer_add(3.0, window=context.window)

        status = BlendNet.addon.managerTaskUploadFilesStatus()
        if wait:
            for retry in range(1, 10):
                status = BlendNet.addon.managerTaskUploadFilesStatus()
                if not status:
                    break
                time.sleep(1)
        if status:
            self.report({'INFO'}, 'Uploading process for task %s: %s' % (self._task_name, status))
            return {'PASS_THROUGH'}

        # Configuring the task
        print('INFO: Configuring task "%s"' % self._task_name)
        self.report({'INFO'}, 'Configuring task "%s"' % self._task_name)
        samples = None
        if scene.cycles.progressive == 'PATH':
            samples = scene.cycles.samples
        elif scene.cycles.progressive == 'BRANCHED_PATH':
            samples = scene.cycles.aa_samples

        # Addon need to pass the actual samples number to the manager
        if scene.cycles.use_square_samples:
            samples *= samples

        cfg = {
            'samples': samples,
            'frame': scene.frame_current,
            'project': fname,
            'use_compositing_nodes': scene.render.use_compositing,
        }

        if not BlendNet.addon.managerTaskConfig(self._task_name, cfg):
            self.report({'WARNING'}, 'Unable to config the task "%s", let\'s retry...' % self._task_name)
            return {'PASS_THROUGH'}

        # Running the task
        self.report({'INFO'}, 'Running task "%s"' % self._task_name)
        if not BlendNet.addon.managerTaskRun(self._task_name):
            self.report({'WARNING'}, 'Unable to start the task "%s", let\'s retry...' % self._task_name)
            return {'PASS_THROUGH'}

        self.report({'INFO'}, 'Task "%s" marked as ready to start' % self._task_name)

        # Ok, task is started - we can clean the name
        self._task_name = None

        if self.is_animation:
            if self._frame < self._frame_to:
                # Not all the frames are processed
                self._frame += 1
                return {'PASS_THROUGH'}
            # Restore the original current frame
            scene.frame_current = self._frame_orig

        # Removing no more required temp blend file
        os.remove(self._project_file)

        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)

        return {'FINISHED'}

class TASKS_UL_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        self.use_filter_sort_alpha = True
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            split = layout.split(factor=0.7)
            split.label(text=item.name)
            split.label(text=('%s:%s' % (item.state[0], item.done)) if item.done and item.state != 'COMPLETED' else item.state)
        elif self.layout_type in {'GRID'}:
            pass

class BlendNetGetNodeLogOperation(bpy.types.Operator):
    bl_idname = 'blendnet.getnodelog'
    bl_label = 'Get Node Log'
    bl_description = 'Show the node (instance) log data'

    node_id: StringProperty(
        name = 'Node ID',
        description = 'ID of the node/instance to get the log',
        default = ''
    )

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        wm = context.window_manager

        data = BlendNet.addon.getNodeLog(self.node_id)
        if not data:
            self.report({'WARNING'}, 'No log data retreived for ' + self.node_id)
            return {'CANCELLED'}
        if data == 'NOT IMPLEMENTED':
            self.report({'WARNING'}, 'Not implemented for the current provider')
            return {'CANCELLED'}
        prefix = self.node_id

        def drawPopup(self, context):
            layout = self.layout

            if BlendNet.addon.showLogWindow(prefix, data):
                layout.label(text='''Don't forget to unlink the file if you '''
                                  '''don't want it to stay in blend file.''')
            else:
                layout.label(text='Unable to show the log window', icon='ERROR')

        wm.popup_menu(drawPopup, title='Log for manager', icon='INFO')

        return {'FINISHED'}

class BlendNetGetServiceLogOperation(bpy.types.Operator):
    bl_idname = 'blendnet.getservicelog'
    bl_label = 'Get Service Log'
    bl_description = 'Show the service (daemon) log data'

    agent_name: StringProperty(
        name = 'Name of Agent',
        description = 'Name of Agent to get log from or Manager will be used',
        default = ''
    )

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        wm = context.window_manager

        out = {}
        if self.agent_name:
            out = BlendNet.addon.agentGetLog(self.agent_name)
        else:
            out = BlendNet.addon.managerGetLog()

        prefix = self.agent_name if self.agent_name else BlendNet.addon.getResources(context).get('manager', {}).get('name')

        if not out:
            self.report({'ERROR'}, 'No log data retreived for ' + prefix)
            return {'CANCELLED'}

        data = []
        line = ''
        for t, l in out.items():
            if not l.endswith('\n'):
                line += l
                continue
            time_str = datetime.fromtimestamp(round(float(t), 3)).strftime('%y.%m.%d %H:%M:%S.%f')
            data.append(time_str + '\t' + line + l)
            line = ''
        if line:
            data.append('{not completed line}\t' + line)

        data = ''.join(data)

        def drawPopup(self, context):
            layout = self.layout

            if BlendNet.addon.showLogWindow(prefix, data):
                layout.label(text='Don\'t forget to unlink the file if you don\'t want it to stay in blend file.')
            else:
                layout.label(text='Unable to show the log window', icon='ERROR')

        wm.popup_menu(drawPopup, title='Log for manager', icon='INFO')

        return {'FINISHED'}

class BlendNetTaskInfoOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskinfo'
    bl_label = 'Task info'
    bl_description = 'Show the current task info panel'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        return len(bn.manager_tasks) > bn.manager_tasks_idx

    def invoke(self, context, event):
        wm = context.window_manager

        def drawPopup(self, context):
            layout = self.layout
            task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
            data = BlendNet.addon.managerTaskStatus(task_name)
            if not data:
                return
            keys = BlendNet.addon.naturalSort(data.keys())
            for key in keys:
                if key == 'result':
                    layout.label(text='%s:' % (key,))
                    for k in data[key]:
                        layout.label(text='  %s: %s' % (k, data[key][k]))
                elif key == 'state_error_info':
                    layout.label(text='%s:' % (key,), icon='ERROR')
                    for it in data[key]:
                        if isinstance(it, dict):
                            for k, v in it.items():
                                layout.label(text='  %s: %s' % (k, v))
                        else:
                            layout.label(text='  ' + str(it))
                else:
                    layout.label(text='%s: %s' % (key, data[key]))

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
        wm.popup_menu(drawPopup, title='Task info for "%s"' % task_name, icon='INFO')

        return {'FINISHED'}

class BlendNetTaskMessagesOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskmessages'
    bl_label = 'Show task messages'
    bl_description = 'Show the task execution messages'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        if len(bn.manager_tasks) <= bn.manager_tasks_idx:
            return False
        task_state = bn.manager_tasks[bn.manager_tasks_idx].state
        return task_state not in {'CREATED', 'PENDING'}

    def invoke(self, context, event):
        wm = context.window_manager

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name

        out = BlendNet.addon.managerTaskMessages(task_name)
        if not out:
            self.report({'ERROR'}, 'No task messages found for "%s"' % (task_name,))
            return {'CANCELLED'}

        data = []
        keys = BlendNet.addon.naturalSort(out.keys())
        for key in keys:
            data.append(key)
            if not out[key]:
                continue
            for line in out[key]:
                data.append('  ' + line)
        data = '\n'.join(data)
        prefix = task_name + 'messages'

        def drawPopup(self, context):
            layout = self.layout

            if BlendNet.addon.showLogWindow(prefix, data):
                layout.label(text='Don\'t forget to unlink the file if you don\'t want it to stay in blend file.')
            else:
                layout.label(text='Unable to show the log window', icon='ERROR')

        wm.popup_menu(drawPopup, title='Task messages for "%s"' % (task_name,), icon='TEXT')

        return {'FINISHED'}

class BlendNetTaskDetailsOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskdetails'
    bl_label = 'Show task details'
    bl_description = 'Show the task execution details'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        if len(bn.manager_tasks) <= bn.manager_tasks_idx:
            return False
        task_state = bn.manager_tasks[bn.manager_tasks_idx].state
        return task_state not in {'CREATED', 'PENDING'}

    def invoke(self, context, event):
        wm = context.window_manager

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name

        out = BlendNet.addon.managerTaskDetails(task_name)
        if not out:
            self.report({'ERROR'}, 'No task details found for "%s"' % (task_name,))
            return {'CANCELLED'}

        data = []
        keys = BlendNet.addon.naturalSort(out.keys())
        for key in keys:
            data.append(key)
            if not out[key]:
                continue
            for line in out[key]:
                data.append('  ' + str(line))
        data = '\n'.join(data)
        prefix = task_name + 'details'

        def drawPopup(self, context):
            layout = self.layout

            if BlendNet.addon.showLogWindow(prefix, data):
                layout.label(text='Don\'t forget to unlink the file if you don\'t want it to stay in blend file.')
            else:
                layout.label(text='Unable to show the log window', icon='ERROR')

        wm.popup_menu(drawPopup, title='Task details for "%s"' % (task_name,), icon='TEXT')

        return {'FINISHED'}

class BlendNetTaskRunOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskrun'
    bl_label = 'Task run'
    bl_description = 'Start the stopped or created task'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        if len(bn.manager_tasks) <= bn.manager_tasks_idx:
            return False
        task_state = bn.manager_tasks[bn.manager_tasks_idx].state
        return task_state in {'CREATED', 'STOPPED'}

    def invoke(self, context, event):
        wm = context.window_manager

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
        BlendNet.addon.managerTaskRun(task_name)

        return {'FINISHED'}

class BlendNetTaskDownloadOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskdownload'
    bl_label = 'Download task result'
    bl_description = 'Download the completed task result'

    result: StringProperty()

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        if len(bn.manager_tasks) <= bn.manager_tasks_idx:
            return False
        task_state = bn.manager_tasks[bn.manager_tasks_idx].state
        # Allow to download results even for error state
        return task_state in {'COMPLETED', 'ERROR'}

    def invoke(self, context, event):
        wm = context.window_manager

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
        result = BlendNet.addon.managerDownloadTaskResult(task_name, self.result)
        if result is None:
            self.report({'WARNING'}, 'Unable to download the final result for %s, please retry later ' % (task_name,))
            return {'CANCELLED'}
        if not result:
            self.report({'INFO'}, 'Downloading the final result for %s... ' % (task_name,))
            return {'FINISHED'}

        self.report({'INFO'}, 'The file is already downloaded and seems the same for %s... ' % (task_name,))
        return {'CANCELLED'}

class BlendNetTaskStopOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskstop'
    bl_label = 'Task stop'
    bl_description = 'Stop the pending, running or error task'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        if len(bn.manager_tasks) <= bn.manager_tasks_idx:
            return False
        task_state = bn.manager_tasks[bn.manager_tasks_idx].state
        return task_state in {'PENDING', 'RUNNING', 'ERROR'}

    def invoke(self, context, event):
        wm = context.window_manager

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
        BlendNet.addon.managerTaskStop(task_name)

        return {'FINISHED'}

class BlendNetTasksStopStartedOperation(bpy.types.Operator):
    bl_idname = 'blendnet.tasksstopstarted'
    bl_label = 'Stop all started tasks'
    bl_description = 'Stop all the pending or running tasks'
    bl_options = {'REGISTER', 'INTERNAL'}

    tasks: CollectionProperty(type=BlendNetManagerTask)

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        wm = context.window_manager
        self.tasks.clear()
        for task in wm.blendnet.manager_tasks:
            if task.state in {'PENDING', 'RUNNING'}:
                self.tasks.add().name = task.name
        return wm.invoke_confirm(self, event)

    def execute(self, context):
        self.report({'INFO'}, 'Stopping %s tasks' % len(self.tasks))
        for task in self.tasks:
            print('INFO: Stopping task "%s"' % task.name)
            BlendNet.addon.managerTaskStop(task.name)
        self.tasks.clear()

        return {'FINISHED'}

class BlendNetTaskRemoveOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskremove'
    bl_label = 'Remove selected task'
    bl_description = 'Remove the task from the tasks list'
    bl_options = {'REGISTER', 'INTERNAL'}

    task_name: StringProperty()

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        if len(bn.manager_tasks) <= bn.manager_tasks_idx:
            return False
        return bn.manager_tasks[bn.manager_tasks_idx].state in {'CREATED', 'STOPPED', 'COMPLETED', 'ERROR'}

    def invoke(self, context, event):
        wm = context.window_manager
        self.task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
        return wm.invoke_confirm(self, event)

    def execute(self, context):
        self.report({'INFO'}, 'Removing task "%s"' % self.task_name)
        BlendNet.addon.managerTaskRemove(self.task_name)

        return {'FINISHED'}

class BlendNetAgentRemoveOperation(bpy.types.Operator):
    bl_idname = 'blendnet.agentremove'
    bl_label = 'Remove the agent'
    bl_description = 'Remove the agent from the agents pool or terminate in case of cloud provider'
    bl_options = {'REGISTER', 'INTERNAL'}

    agent_name: StringProperty()

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

    def execute(self, context):
        self.report({'INFO'}, 'Removing agent "%s"' % self.agent_name)

        prefs = bpy.context.preferences.addons[__package__].preferences
        if prefs.resource_provider == 'local':
            if not BlendNet.addon.managerAgentRemove(self.agent_name):
                self.report({'WARNING'}, 'Unable to remove agent "%s"' % (self.agent_name,))
                return {'CANCELLED'}

            self.report({'INFO'}, 'Removed agent "%s"' % (self.agent_name,))
        else:
            BlendNet.addon.destroyAgent(self.agent_name)
            self.report({'INFO'}, 'BlendNet destroy Agent instance ' + self.agent_name)

        return {'FINISHED'}

class BlendNetAgentCreateOperation(bpy.types.Operator):
    bl_idname = 'blendnet.agentcreate'
    bl_label = 'Agent create'
    bl_description = 'Register new agent in the manager'

    agent_name: StringProperty(
        name = 'Name',
        description = 'Name of Agent to create',
        default = ''
    )

    agent_address: StringProperty(
        name = 'Address',
        description = 'IP or domain name of the agent',
        default = ''
    )

    agent_port: IntProperty(
        name = 'Port',
        description = 'TLS tcp port to communicate Manager with Agent service',
        min = 1,
        max = 65535,
        default = 9443,
    )

    agent_user: StringProperty(
        name = 'User',
        description = 'HTTP Basic Auth username',
        maxlen = 32,
        default = '',
    )

    agent_password: StringProperty(
        name = 'Password',
        description = 'HTTP Basic Auth password',
        subtype = 'PASSWORD',
        maxlen = 128,
        default = '',
    )

    @classmethod
    def poll(cls, context):
        return BlendNet.addon.isManagerActive()

    def invoke(self, context, event):
        wm = context.window_manager

        prefs = bpy.context.preferences.addons[__package__].preferences
        self.agent_port = prefs.agent_port
        self.agent_user = prefs.agent_user
        self.agent_password = prefs.agent_password_hidden

        return wm.invoke_props_dialog(self)

    def execute(self, context):
        if not self.agent_name:
            self.report({'ERROR'}, 'No agent name is specified')
            return {'PASS_THROUGH'}
        if not self.agent_address:
            self.report({'ERROR'}, 'No agent address is specified')
            return {'PASS_THROUGH'}

        cfg = {
            'address': self.agent_address,
            'port': self.agent_port,
            'auth_user': self.agent_user,
            'auth_password': self.agent_password,
        }
        if not BlendNet.addon.managerAgentCreate(self.agent_name, cfg):
            self.report({'WARNING'}, 'Unable to create agent "%s"' % (self.agent_name,))
            return {'PASS_THROUGH'}

        self.report({'INFO'}, 'Created agent "%s" (%s:%s)' % (
            self.agent_name, self.agent_address, self.agent_port
        ))

        return {'FINISHED'}

class BlendNetTasksRemoveEndedOperation(bpy.types.Operator):
    bl_idname = 'blendnet.tasksremoveended'
    bl_label = 'Remove all ended tasks'
    bl_description = 'Remove all the stopped or completed tasks'
    bl_options = {'REGISTER', 'INTERNAL'}

    tasks: CollectionProperty(type=BlendNetManagerTask)

    @classmethod
    def poll(cls, context):
        return True

    def invoke(self, context, event):
        wm = context.window_manager
        self.tasks.clear()
        for task in wm.blendnet.manager_tasks:
            if task.state in {'STOPPED', 'COMPLETED'}:
                self.tasks.add().name = task.name

        return wm.invoke_confirm(self, event)

    def execute(self, context):
        self.report({'INFO'}, 'Removing %s tasks' % len(self.tasks))
        for task in self.tasks:
            print('INFO: Removing task "%s"' % task.name)
            BlendNet.addon.managerTaskRemove(task.name)
        self.tasks.clear()

        return {'FINISHED'}

class BlendNetTaskMenu(bpy.types.Menu):
    bl_idname = 'RENDER_MT_blendnet_task_menu'
    bl_label = 'Task Menu'
    bl_description = 'Allow to operate on tasks in the list'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        return len(bn.manager_tasks) > bn.manager_tasks_idx

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        if not wm.blendnet.manager_tasks:
            layout.label(text='No tasks in the list')
            return

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name

        layout.label(text='Task "%s":' % task_name)
        layout.operator('blendnet.taskinfo', icon='INFO')
        layout.operator('blendnet.taskmessages', icon='TEXT')
        layout.operator('blendnet.taskdetails', icon='TEXT')
        layout.operator('blendnet.taskdownload', text='Download render', icon='DOWNARROW_HLT').result = 'render'
        layout.operator('blendnet.taskdownload', text='Download compose', icon='DOWNARROW_HLT').result = 'compose'
        layout.operator('blendnet.taskrun', icon='PLAY')
        layout.operator('blendnet.taskremove', icon='TRASH')
        layout.operator('blendnet.taskstop', icon='PAUSE')
        layout.label(text='All tasks actions:')
        layout.operator('blendnet.tasksstopstarted', text='Stop all started tasks', icon='PAUSE')
        layout.operator('blendnet.tasksremoveended', text='Remove all ended tasks', icon='TRASH')

class BlendNetRenderPanel(bpy.types.Panel):
    bl_idname = 'RENDER_PT_blendnet_render'
    bl_label = 'BlendNet'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        # Allow to see the tasks if selected blendnet and support cycles
        return context.scene.render.engine in ('CYCLES', __package__)

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        bn = context.scene.blendnet
        prefs = context.preferences.addons[__package__].preferences

        box = layout.box()
        row = box.row()
        row.label(text='BlendNet Render (%s)' % (prefs.resource_provider,))
        row.label(text=context.window_manager.blendnet.status)
        row = box.row()
        row.use_property_split = True
        row.use_property_decorate = False # No prop animation
        row.prop(bn, 'scene_memory_req', text='Render RAM (GB)')

        if not BlendNet.addon.checkAgentMemIsEnough():
            box.label(text='WARN: Agent does not have enough memory to render the scene', icon='ERROR')
        if not prefs.agent_use_cheap_instance:
            box.label(text='WARN: No cheap VMs available, check addon settings', icon='ERROR')
        if not BlendNet.addon.checkProviderIsGood(prefs.resource_provider):
            box.label(text='ERROR: Provider init failed, check addon settings', icon='ERROR')
        if context.scene.render.engine != __package__:
            row = box.row(align=True)
            row.operator('blendnet.runtask', text='Run Image Task', icon='RENDER_STILL').is_animation = False
            row.operator('blendnet.runtask', text='Run Animation Tasks', icon='RENDER_ANIMATION').is_animation = True
        if BlendNet.addon.isManagerActive():
            box.template_list('TASKS_UL_list', '', wm.blendnet, 'manager_tasks', wm.blendnet, 'manager_tasks_idx', rows=1)
            split = box.split(factor=0.8)
            split.operator('blendnet.taskpreview', text='Task Preview', icon='RENDER_RESULT')
            split.menu('RENDER_MT_blendnet_task_menu', text='Actions')

class BlendNetManagerPanel(bpy.types.Panel):
    bl_idname = 'RENDER_PT_blendnet_manager'
    bl_parent_id = 'RENDER_PT_blendnet_render'
    bl_label = ' '
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        layout = self.layout

        layout.label(text='Manager')
        layout.label(text='%s' % BlendNet.addon.getManagerStatus())
        prefs = bpy.context.preferences.addons[__package__].preferences
        if prefs.resource_provider != 'local':
            layout.operator('blendnet.togglemanager', icon='ADD' if not BlendNet.addon.isManagerStarted() else 'X')
            layout.operator('blendnet.destroymanager', icon='TRASH')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False # No prop animation
        prefs = bpy.context.preferences.addons[__package__].preferences

        if prefs.resource_provider != 'local':
            row = layout.row()
            row.enabled = not BlendNet.addon.isManagerCreated()
            row.prop(prefs, 'manager_instance_type', text='Type')
            price = BlendNet.addon.getManagerPriceBG(prefs.manager_instance_type, context)
            row = layout.row()
            if price[0] < 0.0:
                row.label(text='WARNING: Unable to find price for the type "%s": %s' % (
                    prefs.manager_instance_type, price[1]
                ), icon='ERROR')
            else:
                row.label(text='Calculated price: ~%s/Hour (%s)' % (round(price[0], 8), price[1]))
        if prefs.resource_provider == 'local':
            split = layout.split(factor=0.3)
            split.label(text='Address')
            split.label(text='%s:%s' % (prefs.manager_address, prefs.manager_port))

        row = layout.row()
        manager_info = BlendNet.addon.getResources(context).get('manager')

        col = row.column()
        col.enabled = BlendNet.addon.isManagerActive()
        col.operator('blendnet.getservicelog', text='Service Log', icon='TEXT').agent_name = ''

        col = row.column()
        col.enabled = BlendNet.addon.isManagerStarted()
        op = col.operator('blendnet.getnodelog', text='Node Log', icon='TEXT')
        op.node_id = manager_info.get('id', '') if manager_info else ''

        if manager_info:
            layout.label(text='Manager instance:')
            box = layout.box()
            for key, value in manager_info.items():
                split = box.split(factor=0.3)
                split.label(text=key)
                split.label(text=str(value))

        if BlendNet.addon.isManagerActive():
            info = BlendNet.addon.requestManagerInfo(context)
            if info:
                layout.label(text='Manager info:')
                box = layout.box()
                blender_version = info.get('blender', {}).get('version_string')
                if blender_version:
                    split = box.split(factor=0.3)
                    split.label(text='blender')
                    split.label(text=blender_version)
                for key, value in info.get('platform', {}).items():
                    split = box.split(factor=0.3)
                    split.label(text=key)
                    split.label(text=str(value))

class BlendNetAgentsPanel(bpy.types.Panel):
    bl_idname = 'RENDER_PT_blendnet_agents'
    bl_parent_id = 'RENDER_PT_blendnet_render'
    bl_label = ' '
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        layout = self.layout

        layout.label(text='Agents (%d)' % BlendNet.addon.getStartedAgentsNumber(context))
        prefs = bpy.context.preferences.addons[__package__].preferences
        if prefs.resource_provider == 'local':
            layout.operator('blendnet.agentcreate', icon='ADD', text='')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False # No prop animation
        prefs = bpy.context.preferences.addons[__package__].preferences

        if prefs.resource_provider != 'local':
            row = layout.row()
            row.prop(prefs, 'manager_agent_instance_type', text='Agents type')
            row.enabled = not BlendNet.addon.isManagerStarted()
            row = layout.row()
            row.prop(prefs, 'manager_agents_max', text='Agents max')
            row.enabled = not BlendNet.addon.isManagerStarted()
            row = layout.row()
            price = BlendNet.addon.getAgentPriceBG(prefs.manager_agent_instance_type, context)
            if price[0] < 0.0:
                row.label(text='ERROR: Unable to find price for the type "%s": %s' % (
                    prefs.manager_agent_instance_type, price[1]
                ), icon='ERROR')
            else:
                row.label(text='Calculated combined price: ~%s/Hour (%s)' % (
                    round(price[0] * prefs.manager_agents_max, 8), price[1]
                ))

            min_price = BlendNet.addon.getMinimalCheapPriceBG(prefs.manager_agent_instance_type, context)
            if min_price > 0.0:
                row = layout.row()
                row.label(text='Minimal combined price: ~%s/Hour' % (
                    round(min_price * prefs.manager_agents_max, 8),
                ))
                if price[0] <= min_price:
                    row = layout.row()
                    row.label(text='ERROR: Selected cheap price is lower than minimal one', icon='ERROR')

        agents = BlendNet.addon.getResources(context).get('agents', {})
        if agents:
            box = layout.box()
            for inst_name in sorted(agents.keys()):
                info = agents[inst_name]
                split = box.split(factor=0.8)
                split.label(text=info.get('name'))
                row = split.row()
                row.enabled = BlendNet.addon.isManagerActive()

                # The Agent status
                if info.get('error'):
                    row.label(icon='ERROR') # You need to check logs
                if info.get('active'):
                    row.label(icon='CHECKMARK') # Agent is active
                elif info.get('started'):
                    row.label(icon='REC') # Node is started, but Agent is initializing
                elif info.get('stopped'):
                    row.label(icon='PAUSE') # Node is stopped
                else:
                    row.label(icon='X') # Node is terminated or unknown state

                row.enabled = bool(info.get('started') or info.get('stopped')) or prefs.resource_provider == 'local'
                if info.get('active'):
                    row.operator('blendnet.getservicelog', text='', icon='TEXT').agent_name = info.get('name', '')
                else:
                    col = row.column()
                    col.operator('blendnet.getnodelog', text='', icon='TEXT').node_id = info.get('id', '')
                    col.enabled = bool(info.get('started'))
                row.operator('blendnet.agentremove', icon='TRASH', text='').agent_name = info.get('name', '')

class BlendNetRenderEngine(bpy.types.RenderEngine):
    '''Continuous render engine allows to switch between the tasks'''
    bl_idname = __package__
    bl_label = "BlendNet (don't use as a primary engine)"
    bl_use_postprocess = True
    bl_use_preview = False

    def __init__(self):
        self._prev_status = None
        self._prev_message = None
        print('DEBUG: Init BlendNet render')

    def __del__(self):
        print('DEBUG: Delete BlendNet render')

    def updateStats(self, status = None, message = None):
        '''To update the status only if something is changed and print into console'''
        status = status or self._prev_status or ''
        message = message or self._prev_message or ''
        self.update_stats(status, message)
        if self._prev_status != status or self._prev_message != message:
            print('INFO: Render status: %s, %s' % (status, message))
            self._prev_status = status
            self._prev_message = message

    def secToTime(self, sec):
        h = sec // 3600
        m = (sec % 3600) // 60
        out = str((sec % 3600) % 60)+'s'
        if h or m:
            out = str(m)+'m'+out
        if h:
            out = str(h)+'h'+out
        return out

    def render(self, depsgraph):
        scene = depsgraph.scene
        wm = bpy.context.window_manager

        # Restore the original scene engine
        if scene.render.engine == __package__:
            scene.render.engine = wm.blendnet.original_render_engine

        scale = scene.render.resolution_percentage / 100.0
        self.size_x = int(scene.render.resolution_x * scale)
        self.size_y = int(scene.render.resolution_y * scale)

        rendering = True
        prev_status = {}
        prev_name = ''
        loaded_final_render = False
        temp_dir = tempfile.TemporaryDirectory(prefix='blendnet-preview_')
        while rendering:
            time.sleep(1.0)

            if self.test_break():
                # TODO: render cancelled
                self.updateStats(None, 'Cancelling...')
                rendering = False

            if len(wm.blendnet.manager_tasks) < wm.blendnet.manager_tasks_idx+1:
                self.updateStats('Please select the task in BlendNet manager tasks list')
                continue

            task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
            if task_name != prev_name:
                result = self.begin_result(0, 0, self.size_x, self.size_y)
                self.end_result(result)
                self.update_result(result)
                prev_name = task_name
                loaded_final_render = False

            status = BlendNet.addon.managerTaskStatus(task_name)
            if not status:
                continue

            self.updateStats(None, '%s: %s' % (task_name, status.get('state')))

            if status.get('state') == 'RUNNING':
                remaining = None
                if status.get('remaining'):
                    remaining = self.secToTime(status.get('remaining'))
                self.updateStats('Rendered samples: %s/%s | Remaining: %s' % (
                    status.get('samples_done'), status.get('samples'),
                    remaining,
                ))

            update_render = None
            if status.get('state') == 'COMPLETED':
                if not loaded_final_render:
                    total_time = self.secToTime((status.get('end_time') or 0) - (status.get('start_time_actual') or 0))
                    out_file = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].received
                    if out_file == 'skipped':
                        # File was skipped by the downloader, so download it to temp dir
                        out_file = BlendNet.addon.managerDownloadTaskResult(task_name, 'compose', temp_dir.name)
                    if out_file and os.path.isfile(out_file):
                        self.updateStats('Got the final result: %s | Task render time: %s' % (out_file, total_time))
                        update_render = out_file
                        loaded_final_render = True
                    else:
                        # File is going to be downloaded by BlendNet.addon.updateManagerTasks() soon
                        self.updateStats('%s | Task render time: %s' % (out_file, total_time))

            elif status.get('result', {}).get('preview') != prev_status.get('result', {}).get('preview'):
                out_file = BlendNet.addon.managerDownloadTaskResult(task_name, 'preview', temp_dir.name)
                if out_file and os.path.isfile(out_file):
                    update_render = out_file
                else:
                    # It's downloading on background, so not store it right now
                    status['result']['preview'] = prev_status.get('result', {}).get('preview')

            if update_render:
                result = self.begin_result(0, 0, self.size_x, self.size_y)
                if os.path.isfile(update_render):
                    try:
                        result.layers[0].load_from_file(update_render)
                        print('DEBUG: Loaded preview layer:', update_render)
                    except Exception as e:
                        print('DEBUG: Unable to load the preview layer:', e)
                        result.load_from_file(update_render)
                        print('DEBUG: Loaded render result file:', update_render)
                else:
                    print('ERROR: Unable to load not existing result file "%s"' % (update_render,))
                self.end_result(result)
                self.update_result(result)

            prev_status = status

            self.update_progress(status.get('samples_done')/status.get('samples', 1))


def initPreferences():
    '''Will init the preferences with defaults'''
    prefs = bpy.context.preferences.addons[__package__].preferences

    # Set defaults for preferences
    # Update resource_provider anyway to set the addon var
    prefs.resource_provider = prefs.resource_provider or BlendNet.addon.getAddonDefaultProvider()

    # Since default for property will be regenerated every restart
    # we generate new session id if the current one is empty
    if prefs.session_id == '':
        prefs.session_id = ''
    if prefs.manager_password_hidden == '':
        prefs.manager_password_hidden = ''
    if prefs.agent_password_hidden == '':
        prefs.agent_password_hidden = ''

    BlendNet.addon.fillAvailableBlenderDists()

    # Getting provider info to make sure all the settings are ok
    # for current provider configuration
    BlendNet.addon.getProviderInfo()

def register():
    bpy.utils.register_class(BlendNetAddonPreferences)
    initPreferences()

    bpy.utils.register_class(BlendNetSceneSettings)
    bpy.utils.register_class(BlendNetManagerTask)
    bpy.utils.register_class(TASKS_UL_list)
    bpy.utils.register_class(BlendNetSessionProperties)
    bpy.utils.register_class(BlendNetRenderEngine)
    bpy.utils.register_class(BlendNetRunTaskOperation)
    bpy.utils.register_class(BlendNetTaskPreviewOperation)
    bpy.utils.register_class(BlendNetTaskInfoOperation)
    bpy.utils.register_class(BlendNetTaskMessagesOperation)
    bpy.utils.register_class(BlendNetTaskDetailsOperation)
    bpy.utils.register_class(BlendNetTaskDownloadOperation)
    bpy.utils.register_class(BlendNetTaskRunOperation)
    bpy.utils.register_class(BlendNetTaskStopOperation)
    bpy.utils.register_class(BlendNetTasksStopStartedOperation)
    bpy.utils.register_class(BlendNetTaskRemoveOperation)
    bpy.utils.register_class(BlendNetTasksRemoveEndedOperation)
    bpy.utils.register_class(BlendNetAgentRemoveOperation)
    bpy.utils.register_class(BlendNetAgentCreateOperation)
    bpy.utils.register_class(BlendNetTaskMenu)
    bpy.utils.register_class(BlendNetGetServiceLogOperation)
    bpy.utils.register_class(BlendNetGetNodeLogOperation)
    bpy.utils.register_class(BlendNetRenderPanel)
    bpy.utils.register_class(BlendNetToggleManager)
    bpy.utils.register_class(BlendNetDestroyManager)
    bpy.utils.register_class(BlendNetManagerPanel)
    bpy.utils.register_class(BlendNetAgentsPanel)

def unregister():
    bpy.utils.unregister_class(BlendNetAgentsPanel)
    bpy.utils.unregister_class(BlendNetManagerPanel)
    bpy.utils.unregister_class(BlendNetToggleManager)
    bpy.utils.unregister_class(BlendNetDestroyManager)
    bpy.utils.unregister_class(BlendNetRenderPanel)
    bpy.utils.unregister_class(BlendNetGetNodeLogOperation)
    bpy.utils.unregister_class(BlendNetGetServiceLogOperation)
    bpy.utils.unregister_class(BlendNetTaskMenu)
    bpy.utils.unregister_class(BlendNetTaskInfoOperation)
    bpy.utils.unregister_class(BlendNetAgentCreateOperation)
    bpy.utils.unregister_class(BlendNetAgentRemoveOperation)
    bpy.utils.unregister_class(BlendNetTasksRemoveEndedOperation)
    bpy.utils.unregister_class(BlendNetTaskRemoveOperation)
    bpy.utils.unregister_class(BlendNetTasksStopStartedOperation)
    bpy.utils.unregister_class(BlendNetTaskStopOperation)
    bpy.utils.unregister_class(BlendNetTaskRunOperation)
    bpy.utils.unregister_class(BlendNetTaskDownloadOperation)
    bpy.utils.unregister_class(BlendNetTaskDetailsOperation)
    bpy.utils.unregister_class(BlendNetTaskMessagesOperation)
    bpy.utils.unregister_class(BlendNetTaskPreviewOperation)
    bpy.utils.unregister_class(BlendNetRunTaskOperation)
    bpy.utils.unregister_class(BlendNetRenderEngine)
    bpy.utils.unregister_class(BlendNetSessionProperties)
    bpy.utils.unregister_class(TASKS_UL_list)
    bpy.utils.unregister_class(BlendNetManagerTask)
    bpy.utils.unregister_class(BlendNetSceneSettings)
    bpy.utils.unregister_class(BlendNetAddonPreferences)

if __name__ == '__main__':
    register()
