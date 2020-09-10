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
    docker exec -i -t blendnet-manager /bin/sh -c 'apt install -y curl unzip' || continue
    echo "Docker containers are running"
    break
done

docker ps
agent1_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' blendnet-agent-1)
agent2_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' blendnet-agent-2)

# Download the test project
# TODO: download depends on the blender version
#curl -fLo test-project.zip 'https://github.com/state-of-the-art/BlendNet/wiki/files/blendnet-test-project-2.82-v0.2.zip'
docker exec -i -t blendnet-manager curl -fLo /tmp/test-project.zip \
    'https://github.com/state-of-the-art/BlendNet/wiki/files/blendnet-test-project-v0.2.zip'
docker exec -i -t blendnet-manager /bin/sh -c 'cd /tmp ; unzip test-project.zip'

for retry in $(seq 1 10); do
    sleep 5
    echo "Check ${retry}"
    docker exec -i -t blendnet-manager curl --user 'None:None' --insecure --max-time 5 "https://localhost:8443/api/v1/status" || continue
    echo "Looks like connected to blendnet-manager"
    break
done

# Add the Agents to the Manager
docker exec -i -t blendnet-manager curl --user 'None:None' --insecure -X PUT \
    "https://localhost:8443/api/v1/agent/agent-1/config" \
    --data '{"address": "'${agent1_ip}'", "port": 9443, "auth_user": "None", "auth_password": "None"}'
docker exec -i -t blendnet-manager curl --user 'None:None' --insecure -X PUT \
    "https://localhost:8443/api/v1/agent/agent-2/config" \
    --data '{"address": "'${agent2_ip}'", "port": 9443, "auth_user": "None", "auth_password": "None"}'

# Uploading the required task dependencies
docker exec -i -t blendnet-manager /bin/sh -c '
cd /tmp/blendnet-test-project*
for f in $(find . -type f -name "*0032*") tex/* test-project.blend; do
    curl --user "None:None" --insecure \
        --header "X-Checksum-Sha1:$(sha1sum "${f}" | cut -d " " -f 1)" \
        --upload-file "${f}" "https://localhost:8443/api/v1/task/test-task-1/file/${f}"
done
'

# Configure the task
docker exec -i -t blendnet-manager curl --user 'None:None' --insecure -X PUT \
    -d '{"samples": 100, "project": "test-project.blend", "frame": 32}' \
    "https://localhost:8443/api/v1/task/test-task-1/config"

# Run the task execution
docker exec -i -t blendnet-manager curl --user 'None:None' --insecure \
    "https://localhost:8443/api/v1/task/test-task-1/run"

mkdir results

# Watch the task execution and save render
for retry in $(seq 1 50); do
    sleep 5
    echo "Check task ${retry}"
    r=$(docker exec -i -t blendnet-manager curl --user 'None:None' --insecure "https://localhost:8443/api/v1/task/test-task-1/status")
    [ "$(echo "${r}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["result"]["render"])')" != "null" ] || continue
    docker exec -i -t blendnet-manager curl --user 'None:None' --insecure \
        "https://localhost:8443/api/v1/task/test-task-1/status/result/render" > results/render.exr
done

# Watch the task execution and save compose
for retry in $(seq 1 10); do
    sleep 5
    echo "Check task ${retry}"
    r=$(docker exec -i -t blendnet-manager curl --user 'None:None' --insecure "https://localhost:8443/api/v1/task/test-task-1/status")
    [ "$(echo "${r}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["result"]["compose"])')" != "null" ] || continue
    fn=$(echo "${r}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["compose_filepath"])')
    docker exec -i -t blendnet-manager curl --user 'None:None' --insecure \
        "https://localhost:8443/api/v1/task/test-task-1/status/result/compose" > "results/$(basename "${fn}")"
done
