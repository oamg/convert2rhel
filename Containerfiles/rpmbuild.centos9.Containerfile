FROM centos:stream9 as base

RUN dnf update -y && dnf clean all

ENV APP_MAIN_DEPS \
    git \
    rpm-build \
    rpmlint \
    python3-devel \
    python3-dbus \
    python3-pexpect \
    python3-six

FROM base as install_main_deps
RUN dnf install -y $APP_MAIN_DEPS

FROM install_main_deps as install_app
WORKDIR data
COPY . .
RUN ["scripts/build_locally.sh"]
