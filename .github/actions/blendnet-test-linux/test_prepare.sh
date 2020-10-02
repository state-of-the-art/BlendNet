#!/bin/sh -xe
# Prepares the necessary resources to run the tests

BLENDER_VERSION=$1
[ "${BLENDER_VERSION}" != '' ] || exit 1

ROOT=$(dirname "$0")/../../..

# Find the required blender version
python3 "${ROOT}/BlendNet/list_blender_versions.py" 'lin' "${BLENDER_VERSION}" | tee /tmp/blender_versions.txt
ver_line=$(grep '^DATA:' /tmp/blender_versions.txt | head -1)
rm -f /tmp/blender_versions.txt
version=$(echo "${ver_line}" | cut -d" " -f2)
checksum=$(echo "${ver_line}" | cut -d" " -f3)
url=$(echo "${ver_line}" | cut -d" " -f4-)

[ "${version}" != '' ] || exit 2
[ "${checksum}" != '' ] || exit 3
[ "${url}" != '' ] || exit 4

# Download the blender archive and unpack it
out_archive=/tmp/$(basename "${url}")
echo "${checksum} -" > sum.txt
curl -fLs "${url}" | tee "${out_archive}" | sha256sum -c sum.txt
rm -f sum.txt
mkdir -p blender
tar -C blender --strip-components=1 --checkpoint=10000 --checkpoint-action=echo='Unpacked %{r}T' -xf "${out_archive}"
rm -f "${out_archive}"

# Create the initial workspace
mkdir -p workspace
openssl req -x509 -nodes -newkey rsa:4096 \
    -keyout workspace/server.key -out workspace/server.crt \
    -days 365 -subj "/C=US/ST=N/L=N/O=N/OU=N/CN=blendet-service"
# Required ca.crt for Manager
cp workspace/server.crt workspace/ca.crt
cp -a "${ROOT}/.github/actions/blendnet-test-linux/test_run_service.sh" workspace
cp -a "${ROOT}/.github/scripts/test_script_addon.py" workspace

# Download the test project
testproject_url='https://github.com/state-of-the-art/BlendNet/wiki/files/blendnet-test-project'
# (not perfect but simple & working for current CI)
if [ "${BLENDER_VERSION}" = '2.80' ]; then
    testproject_url="${testproject_url}-2.80"
else
    testproject_url="${testproject_url}-2.82"
fi
testproject_url="${testproject_url}-v0.3.zip"

curl -fLo test-project.zip "${testproject_url}"
unzip -d workspace test-project.zip
mv workspace/blendnet-test-project* workspace/test-project
