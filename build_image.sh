#!/bin/bash

set -e

VERSION=$1
echo "VERSION: $VERSION"

docker build \
		-t dicehub/dpm:$VERSION \
		--build-arg VERSION="${VERSION}" \
		.
