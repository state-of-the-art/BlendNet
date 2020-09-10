#!/bin/sh -xe
# Runs the actual test

BLENDER_VERSION=$1
[ "${BLENDER_VERSION}" != '' ] || exit 1

ROOT=$(dirname "$0")/..

# Wait till the services will be started
for retry in $(seq 1 15); do
    sleep 5
    [ $(docker ps -q | wc -l) -gt 2 ] || continue
    # There is no direct access to the Manager port, so using it to run required commands
    # Install curl and unzip to the Manager
    docker exec blendnet-manager /bin/sh -c 'apt install -y curl unzip' || continue
    echo "Docker containers are running"
    break
done

docker ps
agent1_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' blendnet-agent-1)
agent2_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' blendnet-agent-2)

# Download the test project
testproject_url='https://github.com/state-of-the-art/BlendNet/wiki/files/blendnet-test-project'
# (not perfect but simple & working for current CI)
if [ "${BLENDER_VERSION}" = '2.80' ]; then
    testproject_url="${testproject_url}-2.80"
else
    testproject_url="${testproject_url}-2.82"
fi
testproject_url="${testproject_url}-v0.3.zip"
docker exec blendnet-manager curl -fLo /tmp/test-project.zip "${testproject_url}"
docker exec blendnet-manager unzip -d /tmp /tmp/test-project.zip

for retry in $(seq 1 10); do
    sleep 5
    echo "Check ${retry}"
    docker exec blendnet-manager curl --user 'None:None' --insecure --max-time 5 --silent \
        "https://localhost:8443/api/v1/status" || continue
    echo "Looks like connected to blendnet-manager"
    break
done

# Add the Agents to the Manager
docker exec blendnet-manager curl --user 'None:None' --insecure -X PUT \
    "https://localhost:8443/api/v1/agent/agent-1/config" \
    --data '{"address": "'${agent1_ip}'", "port": 9443, "auth_user": "None", "auth_password": "None"}'
docker exec blendnet-manager curl --user 'None:None' --insecure -X PUT \
    "https://localhost:8443/api/v1/agent/agent-2/config" \
    --data '{"address": "'${agent2_ip}'", "port": 9443, "auth_user": "None", "auth_password": "None"}'

# Uploading the required task dependencies
docker exec blendnet-manager /bin/sh -c '
cd /tmp/blendnet-test-project*
for f in $(find . -type f -name "*0032*") tex/* test-project.blend; do
    curl --user "None:None" --insecure \
        --header "X-Checksum-Sha1:$(sha1sum "${f}" | cut -d " " -f 1)" \
        --upload-file "${f}" "https://localhost:8443/api/v1/task/test-task-1/file/${f}"
done
'

# Configure the task (render-ci and compose-ci uses 23 samples)
docker exec blendnet-manager curl --user 'None:None' --insecure -X PUT \
    -d '{"samples": 23, "project": "test-project.blend", "frame": 32}' \
    "https://localhost:8443/api/v1/task/test-task-1/config"

# Run the task execution
docker exec blendnet-manager curl --user 'None:None' --insecure \
    "https://localhost:8443/api/v1/task/test-task-1/run"

mkdir -p results

# Watch the task execution and save render
for retry in $(seq 1 50); do
    sleep 5
    echo "Check task render ${retry}"
    r=$(docker exec blendnet-manager curl --user 'None:None' --insecure --silent \
        "https://localhost:8443/api/v1/task/test-task-1/status")
    [ "$(echo "${r}" | jq -r '.data.result.render')" != "null" ] || continue
    docker exec blendnet-manager curl --user 'None:None' --insecure --output - --silent \
        "https://localhost:8443/api/v1/task/test-task-1/status/result/render" > results/render.exr
    break
done

[ -f results/render.exr ] # Render file exists
ls -lh results/render.exr
file results/render.exr
file results/render.exr | grep -q 'OpenEXR image data' # It's EXR format
file results/render.exr | grep -q 'compression: zip' # Compression is lossless
if [ "${BLENDER_VERSION}" = '2.80' ]; then
    [ $(stat --format '%s' results/render.exr) -gt $((2*1024*1024)) ] # Render EXR size > 2MB
else
    [ $(stat --format '%s' results/render.exr) -gt $((14*1024*1024)) ] # Render EXR size > 14MB
fi

# Watch the task execution and save compose
fn='notexist'
for retry in $(seq 1 10); do
    sleep 5
    echo "Check task compose ${retry}"
    r=$(docker exec blendnet-manager curl --user 'None:None' --insecure --silent \
        "https://localhost:8443/api/v1/task/test-task-1/status")
    [ "$(echo "${r}" | jq -r '.data.result.compose')" != "null" ] || continue
    fn=$(echo "${r}" | jq -r '.data.compose_filepath')
    docker exec blendnet-manager curl --user 'None:None' --insecure --output - --silent \
        "https://localhost:8443/api/v1/task/test-task-1/status/result/compose" > "results/$(basename "${fn}")"
    break
done

compose_file="results/$(basename ${fn})"
[ -f "${compose_file}" ] # Compose file exists
ls -lh "${compose_file}"
file "${compose_file}"
file "${compose_file}" | grep -q 'PNG image data' # It's PNG format
file "${compose_file}" | grep -q '1280 x 720' # Resolution is ok
file "${compose_file}" | grep -q '8-bit/color RGB' # Color is encoded properly
[ $(stat --format '%s' "${compose_file}") -gt $((540*1024)) ] # Compose PNG size > 540KB

echo "Render & Compose images are saved"
