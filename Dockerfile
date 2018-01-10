# Usage (given build times depend on machine):
#
#    Build (rebuild) image:
#    docker build -t dicehub/dpm:dev --build-arg VERSION="${VERSION}" .
#
#    Clean (remove intermidiet images):
#    docker rmi -f $(docker images -f "dangling=true" -q)
#
#    Run image:
#    docker run --name dpm dicehub/dpm:latest-dev python3 -m dpm version
#
#    Build app:
#    docker run --rm -it -v `pwd`:/home/dpm dicehub/dpm:dev python3 -m dpm build /home/dpm -o /home/dpm

FROM python:3.6.2-alpine

ARG VERSION

RUN adduser -D -u 1000 dpm &&\
    chmod -R 700 /home/dpm

# install console and dpm
RUN apk update &&\
    apk add --no-cache bash=4.3.42-r5 &&\
    apk add --no-cache build-base &&\
    pip install https://github.com/dicehub/dpm/archive/$VERSION.zip

WORKDIR /home/dpm
USER dpm
CMD ["python3", "-m", "dpm"]
