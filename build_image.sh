#!/bin/bash

set -e

VERSION=$1
echo "VERSION: $VERSION"

docker build \
		-t dicehub/dpm:$VERSION \
		-t $CI_REGISTRY_IMAGE:$CI_BUILD_TAG \
		--build-arg VERSION="${VERSION}" \
		.
