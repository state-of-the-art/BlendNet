#!/bin/sh -xe
# Runs the required service (manager/agent/addon) in test env

SVC=$1

[ "${SVC}" = 'agent' -o "${SVC}" = 'manager' -o "${SVC}" = 'addon' ] || exit 1
[ -d /srv/scripts/addons/blendnet ] || exit 2
[ -d /srv/blender ] || exit 3
[ -d /srv/workspace ] || exit 4

cp -a /srv/workspace /workspace
cd /workspace

apt update
apt install --no-install-recommends -y libxrender1 libxi6 libgl1

if [ "${SVC}" = "addon" ]; then
    export BLENDER_USER_SCRIPTS=/srv/scripts
    /srv/blender/blender -b -noaudio test-project/test-project.blend -P /srv/workspace/test_script_addon.py
else
    /srv/blender/blender -b -noaudio -P /srv/scripts/addons/blendnet/${SVC}.py
fi
