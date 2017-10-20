# Usage (given build times depend on machine):
#
#    Build (rebuild) image:
#    docker build -t dicehub/dpm:dev .
#
#    Clean (remove intermidiet images):
#    docker rmi -f $(docker images -f "dangling=true" -q)
#
#    Run image:
#    docker run --name dpm dicehub/dpm:latest-dev python3 -m dpm version
#

FROM python:3.6.2-alpine

ARG VERSION

# install console and dpm
RUN apk add --no-cache bash=4.3.42-r5 &&\
    pip install https://github.com/dicehub/dpm/archive/$VERSION.zip
