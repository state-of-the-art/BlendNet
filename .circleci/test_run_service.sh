#!/bin/sh -xe
# Runs the required service (manager/agent) in test env

SVC=$1

[ "${SVC}" = 'agent' -o "${SVC}" = 'manager' ] || exit 1
[ -d /srv/blendnet ] || exit 2
[ -d /srv/blender ] || exit 3
[ -d /srv/workspace ] || exit 4

cp -a /srv/workspace /workspace
cd /workspace

apt update
apt install --no-install-recommends -y libxrender1 libxi6 libgl1

/srv/blender/blender -b -noaudio -P /srv/blendnet/${SVC}.py
