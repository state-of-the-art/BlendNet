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

# Read current task specification from json file
task = None
with open(sys.argv[-1], 'r') as f:
    task = json.load(f)

import bpy

bpy.ops.wm.open_mainfile(filepath=task['project'])

scene = bpy.context.scene

# Enable compose to replace the regular render layers with prerender EXR
scene.render.use_compositing = True
scene.render.use_sequencer = False
scene.use_nodes = True

image_node = scene.node_tree.nodes.new(type='CompositorNodeImage')
bpy.ops.image.open(filepath=task.get('render_file_path'), use_sequence_detection=False)
image_node.image = bpy.data.images[bpy.path.basename(task.get('render_file_path'))]

link_name_overrides = {}
if image_node.image.type == 'MULTILAYER':
    image_node.layer = 'View Layer'
    link_name_overrides['Image'] = 'Combined'

nodes_to_remove = []
links_to_create = []
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

for output, link in links_to_create:
    print('INFO: Connecting "%s" output to %s.%s input' % (
        output, link.to_node, link.to_socket
    ))
    scene.node_tree.links.new(output, link.to_socket)

for node in nodes_to_remove:
    print('INFO: Removing %s' % (node,))
    scene.node_tree.nodes.remove(node)

# Set the output file
scene.render.filepath = '//' + os.path.join(task.get('result_dir'), bpy.path.basename(scene.render.filepath))
bpy.ops.render.render(write_still=True)

print('INFO: Compositing completed')
