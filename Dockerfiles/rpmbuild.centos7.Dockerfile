FROM centos:7 as base

RUN yum update -y && yum clean all

ENV APP_MAIN_DEPS \
    git \
    rpm-build \
    rpmlint \
    python-devel \
    python-setuptools \
    pexpect \
    python-six

FROM base as install_main_deps
RUN yum install -y $APP_MAIN_DEPS

FROM install_main_deps as install_app
WORKDIR data
COPY . .
RUN ["scripts/build_locally.sh"]
