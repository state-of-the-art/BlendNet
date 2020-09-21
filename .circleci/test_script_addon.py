#!blender -b -noaudio -P
# CI script to test the BlendNet Addon send task to Manager

import os
import sys
import time

import bpy

print('INFO: CI: Enabling BlendNet addon')
bpy.ops.preferences.addon_enable(module='blendnet')

print('INFO: CI: Configuring BlendNet addon')
prefs = bpy.context.preferences.addons['blendnet'].preferences

prefs.resource_provider = 'local'
print('INFO: CI: Using provider:', prefs.resource_provider)

prefs.manager_address = 'blendnet-manager-host' # Using presetup docker container DN
prefs.manager_ca_path = os.path.abspath('workspace/ca.crt')
prefs.manager_user = 'None'
prefs.manager_password = 'None'

prefs.agent_user = 'None'
prefs.agent_password = 'None'

print('INFO: CI: Setup scene')
scene = bpy.context.scene
scene.render.engine = 'CYCLES'

# Set the number of samples to CI level
scene.cycles.samples = 23
scene.cycles.aa_samples = 23

# Wait manager connected
for retry in range(1, 10):
    print('INFO: CI: Wait for the Manager active, retry:', retry)
    if bpy.ops.blendnet.agentcreate.poll():
        break
    time.sleep(5)
if not bpy.ops.blendnet.agentcreate.poll():
    print('ERROR: CI: BlendNet Manager was not connected to setup Agents')
    sys.exit(1)

print('INFO: CI: Attaching the Agents to clean the environment')
for i in {1,2}:
    print('INFO: CI: Connecting Agent', i)
    bpy.ops.blendnet.agentcreate(
        'EXEC_DEFAULT',
        agent_name='agent-{}'.format(i),
        agent_address='blendnet-agent-{}-host'.format(i), # Using presetup docker container DN
        agent_port=prefs.agent_port, # Defaults is set in invoke, so reproducing
        agent_user=prefs.agent_user,
        agent_password=prefs.agent_password_hidden,
    )

print('INFO: CI: Run the BlendNet Image Task')
bpy.ops.blendnet.runtask()

print('INFO: CI: Waiting for the compose result file')
for retry in range(1, 50):
    if os.path.isfile(scene.render.frame_path()):
        break
    time.sleep(5)
    print('INFO: CI: Retry to check the compose file "{}" downloaded ({})'.format(scene.render.frame_path(), retry))
    sys.stdout.flush()

print('INFO: CI: Remove the Agents to clean the environment')
for i in {1,2}:
    print('INFO: CI: Disconnecting Agent', i)
    bpy.ops.blendnet.agentremove(
        'EXEC_DEFAULT',
        agent_name='agent-{}'.format(i),
    )

# Check the result
if not os.path.isfile(scene.render.frame_path()):
    print('ERROR: CI: BlendNet did not downloaded the compose file')
    sys.exit(2)

print('DATA: CI:', scene.render.frame_path())
sys.stdout.flush()
