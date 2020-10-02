#!/bin/sh -xe
# Runs the agent in docker container

TEST_NAME=$1
AGENT_NUM=$2

logfile="results/${TEST_NAME}/agent-${AGENT_NUM}.log"
mkdir -p "$(dirname "${logfile}")"

docker run --name blendnet-agent-${AGENT_NUM} -m 2G --rm -i \
    --volumes-from blendnet-srv ubuntu:20.04 \
    /srv/workspace/test_run_service.sh agent > "${logfile}" 2>&1 || true

grep '^Traceback' "${logfile}" && exit 1 || echo "ok - no exceptions in ${logfile}"
grep '^ERROR: ' "${logfile}" && exit 2 || echo "ok - no errors in ${logfile}"
grep '^Fatal Python error: ' "${logfile}" && exit 3 || echo "ok - no python errors in ${logfile}"
