#!/bin/sh -xe
# Runs the actual test

BLENDER_VERSION=$1
[ "${BLENDER_VERSION}" != '' ] || exit 1

ROOT=$(dirname "$0")/..

# Wait till the services will be started
for retry in $(seq 1 15); do
    sleep 5
    docker ps | grep blendnet-executor || continue
    break
done

echo "Docker containers are running"
docker ps

results_dir=results/addon
mkdir -p "${results_dir}"

# Run the execution of BlendNet Addon test script
docker exec blendnet-executor /srv/workspace/test_run_service.sh addon 2>&1 | tee "${results_dir}/addon.log" || true

# Check existing of the path in the log
grep 'DATA: CI:' "${results_dir}/addon.log"

# Copy the compose file to results
remote_file="$(grep 'DATA: CI:' "${results_dir}/addon.log" | cut -d' ' -f3-)"
docker cp "blendnet-executor:${remote_file}" "${results_dir}"

compose_file="${results_dir}/$(basename ${remote_file})"
[ -f "${compose_file}" ] # Compose file exists
ls -lh "${compose_file}"
file "${compose_file}"
file "${compose_file}" | grep -q 'PNG image data' # It's PNG format
file "${compose_file}" | grep -q '1280 x 720' # Resolution is ok
file "${compose_file}" | grep -q '8-bit/color RGB' # Color is encoded properly
[ $(stat --format '%s' "${compose_file}") -gt $((540*1024)) ] # Compose PNG size > 540KB

echo "Check exceptions in the log"
grep '^Traceback' "${results_dir}/addon.log" && exit 1 || echo ok
echo "Check errors in the log"
grep '^ERROR: ' "${results_dir}/addon.log" && exit 2 || echo ok
grep '^Fatal Python error: ' "${results_dir}/addon.log" && exit 3 || echo ok

echo "Addon Compose images are received"
