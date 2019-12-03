bl_info = {
    'name': 'BlendNet - distributed cloud render',
    'author': 'www.state-of-the-art.io',
    'version': (0, 1, 0),
    'blender': (2, 80, 0),
    'location': 'Properties --> Render --> BlendNet Render',
    'description': 'Allows to easy allocate resources in cloud and '
                   'run the cycles rendering with getting preview '
                   'and results.',
    'wiki_url': 'https://github.com/state-of-the-art/BlendNet/wiki',
    'tracker_url': 'https://github.com/state-of-the-art/BlendNet/issues',
    'category': 'Render',
    'warning': 'Experimental release',
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
import hashlib
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

    cloud_provider: EnumProperty(
        name = 'Cloud Provider',
        description = 'Cloud provider to allocate resources for rendering.',
        items = BlendNet.addon.getProvidersEnumItems(),
        update = lambda self, context: BlendNet.addon.selectProvider(self.cloud_provider),
    )

    # Advanced
    session_id: StringProperty(
        name = 'Session ID',
        description = 'Identifier of the session and allocated resources. '
                      'It is used to properly find your resources in the GCP '
                      'project and separate your resources from the other ones. '
                      'Warning: Please be careful with this option and don\'t '
                      'change it if you don\'t know what it\'s doing.',
        maxlen = 12,
        update = lambda self, context: BlendNet.addon.genSID(self, 'session_id'),
    )

    manager_address: StringProperty(
        name = 'Address',
        description = 'If you using the existing Manager service put address here '
                      '(it will be automatically created otherwise)',
        default = '',
    )

    manager_port: IntProperty(
        name = 'Port',
        description = 'TLS tcp port to communicate Addon with Manager service.',
        min = 1,
        max = 65535,
        default = 8443,
    )

    manager_user: StringProperty(
        name = 'User',
        description = 'HTTP Basic Auth username (will be generated if empty).',
        maxlen = 32,
        default = 'blendnet-manager',
    )

    manager_password: StringProperty(
        name = 'Password',
        description = 'HTTP Basic Auth password (will be generated if empty).',
        maxlen = 128,
        default = '',
        update = lambda self, context: BlendNet.addon.hidePassword(self, 'manager_password'),
    )

    agent_port: IntProperty(
        name = 'Port',
        description = 'TLS tcp port to communicate Manager with Agent service.',
        min = 1,
        max = 65535,
        default = 9443,
    )

    agent_user: StringProperty(
        name = 'User',
        description = 'HTTP Basic Auth username (will be generated if empty).',
        maxlen = 32,
        default = 'blendnet-agent',
    )

    agent_password: StringProperty(
        name = 'Password',
        description = 'HTTP Basic Auth password (will be generated if empty).',
        maxlen = 128,
        default = '',
        update = lambda self, context: BlendNet.addon.hidePassword(self, 'agent_password'),
    )

    # Hidden
    show_advanced: BoolProperty(
        name = 'Advanced Properties',
        description = 'Show/Hide the advanced properties',
        default = False
    )

    manager_password_hidden: StringProperty(
        update = lambda self, context: BlendNet.addon.genPassword(self, 'manager_password_hidden'),
    )

    agent_password_hidden: StringProperty(
        update = lambda self, context: BlendNet.addon.genPassword(self, 'agent_password_hidden'),
    )

    def draw(self, context):
        layout = self.layout

        # Cloud provider
        box = layout.box()
        box.prop(self, 'cloud_provider')
        box = box.box()
        box.label(text='Collected cloud info:')

        provider_info = BlendNet.addon.getProviderInfo(context)
        # TODO: Add warnings about low quotas or improper configs
        for key, value in provider_info.items():
            split = box.split(factor=0.5)
            split.label(text=key, icon='ERROR' if key == 'ERROR' else 'DOT')
            split.label(text=value)

        # Advanced properties panel
        advanced_icon = 'TRIA_RIGHT' if not self.show_advanced else 'TRIA_DOWN'
        box = layout.box()
        box.prop(self, 'show_advanced', emboss=False, icon=advanced_icon)

        if self.show_advanced:
            row = box.row()
            row.prop(self, 'session_id')
            box_box = box.box()
            box_box.label(text='Manager')
            row = box_box.row()
            row.prop(self, 'manager_address')
            row.enabled = False # TODO: remove it when functionality will be available
            row = box_box.row()
            row.prop(self, 'manager_port')
            row = box_box.row()
            row.prop(self, 'manager_user')
            row = box_box.row()
            row.prop(self, 'manager_password')
            box_box = box.box()
            box_box.label(text='Agent')
            row = box_box.row()
            row.prop(self, 'agent_port')
            row = box_box.row()
            row.prop(self, 'agent_user')
            row = box_box.row()
            row.prop(self, 'agent_password')

class BlendNetSceneSettings(bpy.types.PropertyGroup):
    manager_instance_type: EnumProperty(
        name = 'Manager size',
        description = 'Selected manager instance size.',
        items = BlendNet.addon.fillAvailableInstanceTypesManager,
    )

    manager_agents_max: IntProperty(
        name = 'Agents max',
        description = 'Maximum number of agents in Manager\'s pool.',
        min = 1,
        max = 65535,
        default = 3,
    )

    manager_agent_instance_type: EnumProperty(
        name = 'Agent size',
        description = 'Selected agent instance size.',
        items = BlendNet.addon.fillAvailableInstanceTypesAgent,
    )

    @classmethod
    def register(cl):
        bpy.types.Scene.blendnet = PointerProperty(
            name = 'BlendNet Settings',
            description = 'BlendNet scene settings',
            type = cl
        )

    @classmethod
    def unregister(cl):
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
    def register(cl):
        bpy.types.WindowManager.blendnet = PointerProperty(
            name = 'BlendNet Session Properties',
            description = 'Just current status of process for internal use',
            type = cl,
        )

    @classmethod
    def unregister(cl):
        if hasattr(bpy.types.WindowManager, 'blendnet'):
            del bpy.types.WindowManager.blendnet

class BlendNetToggleManager(bpy.types.Operator):
    bl_idname = 'blendnet.togglemanager'
    bl_label = ''
    bl_description = 'Start/Stop manager instance'

    retry_counter = 50

    @classmethod
    def poll(cls, context):
        return context.window_manager.blendnet.status == 'idle'

    def invoke(self, context, event):
        BlendNetToggleManager.retry_counter = 50
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
        self.timer = wm.event_timer_add(5.0, window=context.window)

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        return self.execute(context)

    def execute(self, context):
        wm = context.window_manager

        BlendNetToggleManager.retry_counter -= 1
        if BlendNetToggleManager.retry_counter < 0:
            self.report({'ERROR'}, 'BlendNet Manager operation reached maximum retries - something bad happened '
                                   'on "%s" stage. Please consult the documentation' % wm.blendnet.status)
            wm.blendnet.status = 'idle'
            BlendNetToggleManager.retry_counter = 50
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

        wm.event_timer_remove(self.timer)
        wm.blendnet.status = 'idle'
        if context.area:
            context.area.tag_redraw()

        BlendNetToggleManager.retry_counter = 50
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

    def invoke(self, context, event):
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
        self.timer = context.window_manager.event_timer_add(0.1, window=context.window)

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Waiting for manager
        if not BlendNet.addon.isManagerActive():
            return {'PASS_THROUGH'}

        return self.execute(context)

    def execute(self, context):
        scene = context.scene

        scene.frame_current = self._frame

        fname = bpy.path.basename(bpy.data.filepath)
        if not self._task_name:
            # If the operation is not completed - reuse the same task name
            d = datetime.utcnow().strftime('%y%m%d%H%M')
            self._task_name = '%s-%s-%d-%s' % (
                BlendNet.addon.passAlphanumString(fname[:-6]),
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
            context.window_manager.event_timer_remove(self.timer)
            self.timer = context.window_manager.event_timer_add(3.0, window=context.window)

        status = BlendNet.addon.managerTaskUploadFilesStatus()
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

        context.window_manager.event_timer_remove(self.timer)

        return {'FINISHED'}

class TASKS_UL_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            split = layout.split(factor=0.7)
            split.label(text=item.name)
            split.label(text=('%s:%s' % (item.state[0], item.done)) if item.done and item.state != 'COMPLETED' else item.state)
        elif self.layout_type in {'GRID'}:
            pass

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
                layout.label(text='%s: %s' % (key, data[key]))

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
        wm.popup_menu(drawPopup, title='Task info for "%s"' % task_name, icon='INFO')

        return {'FINISHED'}

class BlendNetTaskMessagesOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskmessages'
    bl_label = 'Export task messages'
    bl_description = 'Export the task execution messages'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        if len(bn.manager_tasks) <= bn.manager_tasks_idx:
            return False
        task_state = bn.manager_tasks[bn.manager_tasks_idx].state
        return task_state not in {'CREATED', 'PENDING'}

    def invoke(self, context, event):
        wm = context.window_manager

        def drawPopupOk(self, context):
            task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
            self.layout.label(text='Task messages exported to %s.%s.messages.txt' % (bpy.data.filepath, task_name))

        def drawPopupNo(self, context):
            task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
            self.layout.label(text='No task messages available for export' % (bpy.data.filepath, task_name))

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name

        data = BlendNet.addon.managerTaskMessages(task_name)
        if data:
            keys = BlendNet.addon.naturalSort(data.keys())
            with open('%s.%s.messages.txt' % (bpy.data.filepath, task_name), 'w') as f:
                for key in keys:
                    f.write('%s%s' % (key, os.linesep))
                    for line in data[key]:
                        f.write('\t%s%s' % (line, os.linesep))

        wm.popup_menu(drawPopupOk if data else drawPopupNo, title='Task messages for "%s"' % task_name, icon='TEXT')

        return {'FINISHED'}

class BlendNetTaskDetailsOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskdetails'
    bl_label = 'Export task details'
    bl_description = 'Export the task execution details'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        if len(bn.manager_tasks) <= bn.manager_tasks_idx:
            return False
        task_state = bn.manager_tasks[bn.manager_tasks_idx].state
        return task_state not in {'CREATED', 'PENDING'}

    def invoke(self, context, event):
        wm = context.window_manager

        def drawPopupOk(self, context):
            task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
            self.layout.label(text='Task details exported to %s.%s.details.txt' % (bpy.data.filepath, task_name))

        def drawPopupNo(self, context):
            task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
            self.layout.label(text='No task details available for export' % (bpy.data.filepath, task_name))

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name

        data = BlendNet.addon.managerTaskDetails(task_name)
        if data:
            keys = BlendNet.addon.naturalSort(data.keys())
            with open('%s.%s.details.txt' % (bpy.data.filepath, task_name), 'w') as f:
                for key in keys:
                    f.write('%s%s' % (key, os.linesep))
                    for line in data[key]:
                        f.write('\t%s%s' % (line, os.linesep))

        wm.popup_menu(drawPopupOk if data else drawPopupNo, title='Task details for "%s"' % task_name, icon='TEXT')

        return {'FINISHED'}

class BlendNetTaskStartOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskstart'
    bl_label = 'Task start'
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

class BlendNetTaskStopOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskstop'
    bl_label = 'Task stop'
    bl_description = 'Stop the pending or running task'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        if len(bn.manager_tasks) <= bn.manager_tasks_idx:
            return False
        task_state = bn.manager_tasks[bn.manager_tasks_idx].state
        return task_state in {'PENDING', 'RUNNING'}

    def invoke(self, context, event):
        wm = context.window_manager

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
        BlendNet.addon.managerTaskStop(task_name)

        return {'FINISHED'}

class BlendNetTaskRemoveOperation(bpy.types.Operator):
    bl_idname = 'blendnet.taskremove'
    bl_label = 'Task remove'
    bl_description = 'Remove the task from the tasks list'

    @classmethod
    def poll(cls, context):
        bn = context.window_manager.blendnet
        return len(bn.manager_tasks) > bn.manager_tasks_idx

    def invoke(self, context, event):
        wm = context.window_manager

        # TODO: ARE YOU SURE popup

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name
        BlendNet.addon.managerTaskRemove(task_name)

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

        task_name = wm.blendnet.manager_tasks[wm.blendnet.manager_tasks_idx].name

        layout.label(text='Task "%s":' % task_name)
        layout.operator('blendnet.taskinfo', icon='INFO')
        layout.operator('blendnet.taskmessages', icon='TEXT')
        layout.operator('blendnet.taskdetails', icon='TEXT')
        layout.operator('blendnet.taskstart', icon='PLAY')
        layout.operator('blendnet.taskremove', icon='TRASH')
        layout.operator('blendnet.taskstop', icon='PAUSE')
        layout.label(text='All tasks actions:')
        layout.operator('blendnet.taskstoprunning', text='Stop all running tasks', icon='PAUSE')
        layout.operator('blendnet.taskremovestopped', text='Remove all stopped tasks', icon='TRASH')

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
        prefs = context.preferences.addons[__package__].preferences

        box = layout.box()
        row = box.row()
        row.label(text='BlendNet Render')
        row.label(text=context.window_manager.blendnet.status)
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
        layout.operator('blendnet.togglemanager', icon='ADD' if not BlendNet.addon.isManagerStarted() else 'X')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False # No prop animation
        bn = context.scene.blendnet

        row = layout.row()
        row.enabled = not BlendNet.addon.isManagerCreated()
        row.prop(bn, 'manager_instance_type', text='Type')

        manager_info = BlendNet.addon.getResources(context).get('manager')
        if manager_info:
            layout.label(text='Manager info:')
            box = layout.box()
            for key, value in manager_info.items():
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

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False # No prop animation
        bn = context.scene.blendnet

        layout.enabled = not BlendNet.addon.isManagerStarted()
        row = layout.row()
        row.prop(bn, 'manager_agent_instance_type', text='Agents type')
        row = layout.row()
        row.prop(bn, 'manager_agents_max', text='Agents max')

class BlendNetRenderEngine(bpy.types.RenderEngine):
    '''Continuous render engine to allow switch between tasks'''
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
        import time
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
            out_path = bpy.path.abspath(scene.render.filepath)
            os.makedirs(out_path, 0o755, True)
            # TODO: make possible to use ### in the out path to save result using frame number
            if status.get('state') == 'COMPLETED':
                if not loaded_final_render:
                    total_time = self.secToTime((status.get('end_time') or 0) - (status.get('start_time_actual') or 0))
                    out_file = os.path.join(out_path, '%s.exr' % task_name)
                    checksum = prev_status.get('result', {}).get('render')
                    # Check the local file first - maybe it's the thing we need
                    if os.path.isfile(out_file):
                        # Calculate sha1 to make sure it's the same file
                        sha1_calc = hashlib.sha1()
                        with open(out_file, 'rb') as f:
                            for chunk in iter(lambda: f.read(1048576), b''):
                                sha1_calc.update(chunk)
                        if sha1_calc.hexdigest() == status.get('result', {}).get('render'):
                            self.updateStats('Got the final render! | Total time: %s' % total_time)
                            update_render = out_file
                            checksum = sha1_calc.hexdigest()
                            loaded_final_render = True

                    # If file is not working for us - than download
                    if checksum != status.get('result', {}).get('render'):
                        self.updateStats('Downloading the final render...')
                        BlendNet.addon.managerTaskResultDownload(task_name, 'render', out_file)
                        self.updateStats('Got the final render! | Total time: %s' % total_time)
                        update_render = out_file
                        loaded_final_render = True
            elif status.get('result', {}).get('preview') != prev_status.get('result', {}).get('preview'):
                out_file = os.path.join(out_path, '%s-preview.exr' % task_name)
                BlendNet.addon.managerTaskResultDownload(task_name, 'preview', out_file)
                update_render = out_file

            if update_render:
                result = self.begin_result(0, 0, self.size_x, self.size_y)
                if os.path.isfile(update_render):
                    result.layers[0].load_from_file(update_render)
                else:
                    print('ERROR: Unable to load not existing result file "%s"' % update_render)
                self.end_result(result)
                self.update_result(result)

            prev_status = status

            self.update_progress(status.get('samples_done')/status.get('samples', 1))


def initPreferences():
    '''Will init the preferences with defaults'''
    import random, string
    prefs = bpy.context.preferences.addons[__package__].preferences

    # Set defaults for preferences
    # Update cloud_provider anyway to set the addon var
    prefs.cloud_provider = prefs.cloud_provider or BlendNet.addon.getAddonDefaultProvider()

    # Since default for property will be regenerated every restart
    # we generate new session id if the current one is empty
    if prefs.session_id == '':
        prefs.session_id = ''
    if prefs.manager_password_hidden == '':
        prefs.manager_password_hidden = ''
    if prefs.agent_password_hidden == '':
        prefs.agent_password_hidden = ''

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
    bpy.utils.register_class(BlendNetTaskStartOperation)
    bpy.utils.register_class(BlendNetTaskStopOperation)
    bpy.utils.register_class(BlendNetTaskRemoveOperation)
    bpy.utils.register_class(BlendNetTaskMenu)
    bpy.utils.register_class(BlendNetRenderPanel)
    bpy.utils.register_class(BlendNetToggleManager)
    bpy.utils.register_class(BlendNetManagerPanel)
    bpy.utils.register_class(BlendNetAgentsPanel)

def unregister():
    bpy.utils.unregister_class(BlendNetAgentsPanel)
    bpy.utils.unregister_class(BlendNetManagerPanel)
    bpy.utils.unregister_class(BlendNetToggleManager)
    bpy.utils.unregister_class(BlendNetRenderPanel)
    bpy.utils.unregister_class(BlendNetTaskMenu)
    bpy.utils.unregister_class(BlendNetTaskInfoOperation)
    bpy.utils.unregister_class(BlendNetTaskRemoveOperation)
    bpy.utils.unregister_class(BlendNetTaskStopOperation)
    bpy.utils.unregister_class(BlendNetTaskStartOperation)
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

if __name__ == "__main__":
    register()
