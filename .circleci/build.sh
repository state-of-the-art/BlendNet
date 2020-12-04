#!/bin/sh -xe
# Show the version and pack the BlendNet distributive archive

ROOT=$(dirname "$0")/..

# Get version from the addon init file
VERSION=$(head -10 "${ROOT}/__init__.py" | grep -o 'version.: *(.*)' | tr ',' '.' | grep -o '[0-9]\|\.' | tr -d '\n')

DEV_VER=''
if [ "x$(head -10 "${ROOT}/__init__.py" | grep -o 'warning.: *.dev')" != 'x' ]; then
    # Mark development version with hash to not confuse with the logs
    GIT_HASH=$(git -C "${ROOT}" rev-parse --short HEAD)
    sed -i "0,/'development version'/{s/'development version'/'dev-${GIT_HASH}'/}" "${ROOT}/__init__.py"
    DEV_VER="-${GIT_HASH}"
fi

echo "INFO: BlendNet version: $VERSION$DEV_VER"
if [ -d blendnet ]; then
    mkdir -p results/dist

    tar -cvzf results/dist/blendnet-${VERSION}${DEV_VER}.tar.gz --exclude='.*' --exclude='__pycache__' blendnet
    zip -9 -r results/dist/blendnet-${VERSION}${DEV_VER}.zip blendnet --exclude '**/.*' '**/__pycache__/*'
    echo "INFO: Created dist archives: $(ls results/dist | tr '\n' ', ')"
else
    echo 'WARN: Skip creating dist archives, no blendnet dir is here'
fi
