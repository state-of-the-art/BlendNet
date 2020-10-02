#!/bin/sh -xe
# Runs the manager in docker container

TEST_NAME=$1

logfile="results/${TEST_NAME}/manager.log"
mkdir -p "$(dirname "${logfile}")"

# Wait for blendnet-agent-1 container
while ! docker ps | grep blendnet-agent-1; do echo "waiting agent-1"; docker ps; sleep 1; done
# Wait for blendnet-agent-2 container
while ! docker ps | grep blendnet-agent-2; do echo "waiting agent-2"; docker ps; sleep 1; done

docker run --name blendnet-manager -m 2G --rm -i \
    --link blendnet-agent-1:blendnet-agent-1-host \
    --link blendnet-agent-2:blendnet-agent-2-host \
    --volumes-from blendnet-srv ubuntu:20.04 \
    /srv/workspace/test_run_service.sh manager > "${logfile}" 2>&1 || true

grep '^Traceback' "${logfile}" && exit 1 || echo "ok - no exceptions in ${logfile}"
grep '^ERROR: ' "${logfile}" && exit 2 || echo "ok - no errors in ${logfile}"
grep '^Fatal Python error: ' "${logfile}" && exit 3 || echo "ok - no python errors in ${logfile}"
