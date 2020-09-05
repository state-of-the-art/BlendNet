#!/usr/bin/python3
# -*- coding: UTF-8 -*-
'''BlendNet Script Compose

Description: Special script used by the Manager to compose result
'''

import signal # The other better ways are not working for subprocess...
signal.signal(signal.SIGTERM, lambda s, f: print('WARN: Dodged TERM subprocess'))

import os, sys, json
sys.path.append(os.path.dirname(__file__))

import disable_buffering
import blend_file

# Read current task specification from json file
task = None
with open(sys.argv[-1], 'r') as f:
    task = json.load(f)

import bpy

exitcode = 0

print('INFO: Loading project file "%s"' % (task.get('project'),))
bpy.ops.wm.open_mainfile(filepath=task.get('project'))

scene = bpy.context.scene

# Set frame if provided
if 'frame' in task:
    scene.frame_current = task['frame']

print('INFO: Checking existance of the dependencies')
blend_file.getDependencies()

if scene.render.is_movie_format:
    print('WARN: Unable to save still image to movie format, so use single-layer exr for compose')
    exitcode = 1
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '32'
    scene.render.image_settings.exr_codec = 'ZIP'

# Return the compose_filepath variable
compose_filepath = scene.render.frame_path()
if scene.render.filepath.startswith('//'):
    # It's relative to blend project path
    compose_filepath = bpy.path.relpath(compose_filepath)
    # Sometimes it's not recognized properly
    if not compose_filepath.startswith('//'):
        compose_filepath = '//' + compose_filepath
print('INFO: Compose filepath: %s' % (compose_filepath,))

# Set the output file
filename = bpy.path.basename(scene.render.frame_path())
scene.render.filepath = os.path.join(task.get('result_dir'), filename)
os.makedirs(bpy.path.abspath(task.get('result_dir')), mode=0o750, exist_ok=True)

bpy.ops.image.open(filepath=bpy.path.abspath(task.get('render_file_path')), use_sequence_detection=False)
image = bpy.data.images[bpy.path.basename(task.get('render_file_path'))]

# If compositing is disabled - just convert the file to the required format
if not task.get('use_compositing_nodes'):
    if scene.render.image_settings.file_format == 'OPEN_EXR_MULTILAYER':
        print('WARN: Just move the render to compose due to blender bug T71087')
        os.rename(bpy.path.abspath(task.get('render_file_path')), bpy.path.abspath(scene.render.frame_path()))
        sys.exit(1)

    # Save the loaded image as render to convert
    image.save_render(bpy.path.abspath(scene.render.frame_path()))

# Enable compose to replace the regular render layers node with prerendered EXR image
scene.render.use_compositing = True
scene.render.use_sequencer = False
scene.use_nodes = True

image_node = scene.node_tree.nodes.new(type='CompositorNodeImage')
image_node.image = image

link_name_overrides = {}
if image_node.image.type == 'MULTILAYER':
    image_node.layer = 'View Layer'
    link_name_overrides['Image'] = 'Combined'

nodes_to_remove = []
links_to_create = []
# Find nodes, links and outpus
for node in scene.node_tree.nodes:
    if not isinstance(node, bpy.types.CompositorNodeRLayers) or node.scene != scene:
        continue
    nodes_to_remove.append(node)
    print('INFO: Reconnecting %s links to render image' % (node,))
    for link in scene.node_tree.links:
        if link.from_node != node:
            continue
        link_name = link_name_overrides.get(link.from_socket.name, link.from_socket.name)
        for output in image_node.outputs:
            if output.name != link_name:
                continue
            links_to_create.append((output, link))
            break

# Relinking previous render layer node outputs to the rendered image
for output, link in links_to_create:
    print('INFO: Connecting "%s" output to %s.%s input' % (
        output, link.to_node, link.to_socket
    ))
    scene.node_tree.links.new(output, link.to_socket)

# Removing the nodes could potentially break the pipeline
for node in nodes_to_remove:
    print('INFO: Removing %s' % (node,))
    scene.node_tree.nodes.remove(node)

bpy.ops.render.render(write_still=True)

print('INFO: Compositing completed')
sys.exit(exitcode)
