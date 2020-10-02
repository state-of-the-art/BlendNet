#!/bin/sh -xe
# Runs the actual test

BLENDER_VERSION=$1
[ "${BLENDER_VERSION}" != '' ] || exit 1

ROOT=$(dirname "$0")/../../..

# Run Agents & Manager containers
"${ROOT}/.github/actions/blendnet-test-linux/test_run_agent.sh" addon 1 &
"${ROOT}/.github/actions/blendnet-test-linux/test_run_agent.sh" addon 2 &
"${ROOT}/.github/actions/blendnet-test-linux/test_run_manager.sh" addon &

# Wait for blendnet-manager container
while ! docker ps | grep blendnet-manager; do echo "waiting manager"; docker ps; sleep 1; done

echo "Docker containers are running"
docker ps

results_dir=results/addon
mkdir -p "${results_dir}"

# Run the execution of BlendNet Addon test script
docker run --name blendnet-executor -m 1G -i \
    --link blendnet-manager:blendnet-manager-host \
    --volumes-from blendnet-srv \
    ubuntu:20.04 /srv/workspace/test_run_service.sh addon 2>&1 | tee "${results_dir}/addon.log" || true

# Stop the Agents & Manager
# TODO: when BN-64 is completed - stop Manager and Agents properly
docker rm -f blendnet-manager || true
docker rm -f blendnet-agent-1 || true
docker rm -f blendnet-agent-2 || true

# Check existing of the path in the log
grep 'DATA: CI:' "${results_dir}/addon.log"

# Copy the compose file to results
remote_file="$(grep 'DATA: CI:' "${results_dir}/addon.log" | cut -d' ' -f3-)"
docker cp "blendnet-executor:${remote_file}" "${results_dir}"
docker rm -f blendnet-executor || true

compose_file="${results_dir}/$(basename ${remote_file})"
[ -f "${compose_file}" ] # Compose file exists
ls -lh "${compose_file}"
file "${compose_file}"
file "${compose_file}" | grep -q 'PNG image data' # It's PNG format
file "${compose_file}" | grep -q '1280 x 720' # Resolution is ok
file "${compose_file}" | grep -q '8-bit/color RGB' # Color is encoded properly
[ $(stat --format '%s' "${compose_file}") -gt $((540*1024)) ] # Compose PNG size > 540KB

grep '^Traceback' "${results_dir}/addon.log" && exit 1 || echo "ok - no exceptions in ${results_dir}/addon.log"
grep '^ERROR: ' "${results_dir}/addon.log" && exit 2 || echo "ok - no errors in ${results_dir}/addon.log"
grep '^Fatal Python error: ' "${results_dir}/addon.log" && exit 3 || echo "ok - no python errors in ${results_dir}/addon.log"

echo "Addon Compose images are received"
