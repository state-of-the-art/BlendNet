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

# There is no direct access to the Manager port, so using it to run required commands
# Install curl and unzip to the Manager
docker exec blendnet-executor /bin/sh -c 'apt install -y curl unzip' || continue
echo "Docker containers are running"

docker ps

for retry in $(seq 1 10); do
    sleep 5
    echo "Check ${retry}"
    docker exec blendnet-executor curl --user 'None:None' --insecure --max-time 5 --silent \
        "https://blendnet-manager-host:8443/api/v1/status" || continue
    echo "Looks like connected to blendnet-manager"
    break
done

# Add the Agents to the Manager
docker exec blendnet-executor curl --user 'None:None' --insecure --silent -X PUT \
    "https://blendnet-manager-host:8443/api/v1/agent/agent-1/config" \
    --data '{"address": "blendnet-agent-1-host", "port": 9443, "auth_user": "None", "auth_password": "None"}'
docker exec blendnet-executor curl --user 'None:None' --insecure --silent -X PUT \
    "https://blendnet-manager-host:8443/api/v1/agent/agent-2/config" \
    --data '{"address": "blendnet-agent-2-host", "port": 9443, "auth_user": "None", "auth_password": "None"}'

# Uploading the required task dependencies
docker exec blendnet-executor /bin/sh -c '
cd /workspace
for f in $(find /workspace/test-project/proj test-project/ext -type f -name "*0032*") test-project/ext/tex/* test-project/proj/test-project.blend; do
    curl --user "None:None" --insecure \
        --header "X-Checksum-Sha1:$(sha1sum "${f}" | cut -d " " -f 1)" \
        --upload-file "${f}" "https://blendnet-manager-host:8443/api/v1/task/test-task-1/file/${f}"
done
'

# Configure the task (render-ci and compose-ci uses 23 samples)
docker exec blendnet-executor curl --user 'None:None' --insecure --silent -X PUT \
    -d '{"samples": 23, "compose_filepath": "newout-32.png", "project": "test-project.blend", "frame": 32, "project_path": "/workspace/test-project/proj", "cwd_path": "/workspace"}' \
    "https://blendnet-manager-host:8443/api/v1/task/test-task-1/config"

# Run the task execution
docker exec blendnet-executor curl --user 'None:None' --insecure --silent \
    "https://blendnet-manager-host:8443/api/v1/task/test-task-1/run"

results_dir=results/api
mkdir -p "${results_dir}"

# Watch the task execution and save render
for retry in $(seq 1 50); do
    sleep 5
    echo "Check task render ${retry}"
    r=$(docker exec blendnet-executor curl --user 'None:None' --insecure --silent \
        "https://blendnet-manager-host:8443/api/v1/task/test-task-1/status")
    [ "$(echo "${r}" | jq -r '.data.result.render')" != "null" ] || continue
    docker exec blendnet-executor curl --user 'None:None' --insecure --output - --silent \
        "https://blendnet-manager-host:8443/api/v1/task/test-task-1/status/result/render" > "${results_dir}/render.exr"
    break
done

render_file="${results_dir}/render.exr"
[ -f "${render_file}" ] # Render file exists
ls -lh "${render_file}"
file "${render_file}"
file "${render_file}" | grep -q 'OpenEXR image data' # It's EXR format
file "${render_file}" | grep -q 'compression: zip' # Compression is lossless
if [ "${BLENDER_VERSION}" = '2.80' ]; then
    [ $(stat --format '%s' "${render_file}") -gt $((2*1024*1024)) ] # Render EXR size > 2MB
else
    [ $(stat --format '%s' "${render_file}") -gt $((5*1024*1024)) ] # Render EXR size > 5MB
fi

# Watch the task execution and save compose
fn='notexist'
for retry in $(seq 1 10); do
    sleep 5
    echo "Check task compose ${retry}"
    r=$(docker exec blendnet-executor curl --user 'None:None' --insecure --silent \
        "https://blendnet-manager-host:8443/api/v1/task/test-task-1/status")
    [ "$(echo "${r}" | jq -r '.data.result.compose')" != "null" ] || continue
    fn=$(echo "${r}" | jq -r '.data.compose_filepath')
    docker exec blendnet-executor curl --user 'None:None' --insecure --output - --silent \
        "https://blendnet-manager-host:8443/api/v1/task/test-task-1/status/result/compose" > "${results_dir}/$(basename "${fn}")"
    break
done

compose_file="${results_dir}/$(basename ${fn})"
[ -f "${compose_file}" ] # Compose file exists
ls -lh "${compose_file}"
file "${compose_file}"
file "${compose_file}" | grep -q 'PNG image data' # It's PNG format
file "${compose_file}" | grep -q '1280 x 720' # Resolution is ok
file "${compose_file}" | grep -q '8-bit/color RGB' # Color is encoded properly
[ $(stat --format '%s' "${compose_file}") -gt $((540*1024)) ] # Compose PNG size > 540KB

echo "Render & Compose images are received"
