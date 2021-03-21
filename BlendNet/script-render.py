#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Script Render

Description: Special script used by the agent to render the task
'''

# Since blender reports status only to stdout - we need this
# separated script to watch on progress from the agent process.
#
# When it will be possible to read the status of render directly
# from python - we will be able to use agent without the script:
# the main trick there - to call open file/render through queue
# from the main thread, because blender hate threading.

import os, sys, json
sys.path.append(os.path.dirname(__file__))

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

import signal # The other better ways are not working for subprocess...
signal.signal(signal.SIGTERM, lambda s, f: eprint('WARN: Dodged TERM subprocess'))

import disable_buffering
import blend_file

# Read current task specification from json file
task = None
with open(sys.argv[-1], 'r') as f:
    task = json.load(f)

import random # To generate seed for rendering
import threading # To run timer and flush render periodically

import bpy

eprint("INFO: Preparing rendering of:", bpy.data.filepath)
scene = bpy.context.scene

# Set some required variables
eprint('INFO: Set scene vars')
scene.render.use_overwrite = True
scene.render.use_compositing = False # Don't use because Composite layer impossible to merge
scene.render.use_sequencer = False # No need for still images

# Switch to use maximum threads possible on the worker
scene.render.threads_mode = 'AUTO'

# scene.cycles.device = 'CPU' # The only one supported right now

eprint('---------------   CUDA, DEVICES & GPU   ------------------')

eprint('INFO: Enable CUDA to nvidia driver')
bpy.context.preferences.addons['cycles'].preferences.compute_device_type = 'CUDA'

eprint('INFO: Enable and list all devices, or optionally disable CPU')
for devices in bpy.context.preferences.addons['cycles'].preferences.get_devices():
    for device in devices:
        device.use = True
        if device.type == 'CPU':
            device.use = False
        eprint("Device '{}' type {} : {}" . format(device.name, device.type, device.use))

eprint('INFO: Set Scene Devices as GPU for Cycles')
scene.cycles.device = 'GPU'

# Disabling square samples - script is getting the real number of samples to render
scene.cycles.use_square_samples = False

# Set sampling
eprint('INFO: Set sampling')
if scene.cycles.progressive == 'PATH':
    scene.cycles.samples = task['samples']
elif scene.cycles.progressive == 'BRANCHED_PATH':
    scene.cycles.aa_samples = task['samples']
else:
    eprint('ERROR: Unable to determine the sampling integrator')
    sys.exit(1)

# Set task seed or use random one (because we need an unique render pattern)
scene.cycles.seed = task.get('seed', random.randrange(0, 2147483647))

# Set frame if provided
if 'frame' in task:
    scene.frame_current = task['frame']

if bpy.context.view_layer.cycles.use_denoising:
    eprint('WARN: Disable denoising but enabling store denoise passes')
    # We have to disable denoising, but ...
    bpy.context.view_layer.cycles.use_denoising = False
    # ... enabling storing of the denoising passes for future processing
    # using _cycles.denoise() or composite denoise node
    bpy.context.view_layer.cycles.denoising_store_passes = True

eprint('INFO: Use progressive refine')
scene.cycles.use_progressive_refine = True

# BN-119 Disabled due to crashes during collecting the statistics
#try:
#    import _cycles
#    _cycles.enable_print_stats() # Show detailed render statistics after the render
#except:
#    pass

eprint('INFO: Checking existance of the dependencies')
goods, bads = blend_file.getDependencies(task.get('project_path'), task.get('cwd_path'), True)

class Commands:
    def savePreview(cls = None):
        scene.render.image_settings.file_format = 'OPEN_EXR'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '32'
        scene.render.image_settings.exr_codec = 'DWAA'
        # Should not be executed on the last sample otherwise will stuck right here
        bpy.data.images['Render Result'].save_render('_preview.exr')
        scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.image_settings.color_depth = '32'
        scene.render.image_settings.exr_codec = 'ZIP'
        # Windows will not just replace the file - so need to check if it's exist
        if os.path.exists('preview.exr'):
            os.remove('preview.exr')
        os.rename('_preview.exr', 'preview.exr')

    def saveRender(cls = None):
        # Due to the bug it's not working properly: https://developer.blender.org/T71087
        # Basically when multilayer exr is selected - it's saved as a regular one layer
        # exr, so switched to `write_still` in executing the render command
        os.rename('_render.exr', 'render.exr')

def executeCommand(name):
    func = getattr(Commands, name, None)
    if callable(func):
        func()
        eprint('INFO: Command "%s" completed' % name)
    else:
        eprint('ERROR: Unable to execute "%s" command' % name)

def stdinProcess():
    '''Is used to get commands from the parent process'''
    for line in iter(sys.stdin.readline, b''):
        try:
            command = line.strip()
            if command == 'end':
                break
            executeCommand(command)
        except Exception as e:
            eprint('ERROR: Exception during processing stdin: %s' % e)

input_thread = threading.Thread(target=stdinProcess)
input_thread.start()
eprint('INFO: Starting render process')

# Start the render process
scene.render.image_settings.file_format = 'OPEN_EXR_MULTILAYER'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.image_settings.color_depth = '32'
scene.render.image_settings.exr_codec = 'ZIP'
scene.render.filepath = os.path.abspath('_render.exr')
bpy.ops.render.render(write_still=True)

eprint('INFO: Render process completed')

# Render complete - saving the result image
executeCommand('saveRender')
# Save the final preview to update the user
executeCommand('savePreview')

eprint('INFO: Save render completed')
