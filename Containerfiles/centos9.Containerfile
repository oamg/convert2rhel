FROM quay.io/centos/centos:stream9 as base

ENV PYTHON python3
ENV PIP pip3
ENV PYTHONDONTWRITEBYTECODE 1

ENV APP_DEV_DEPS "requirements/centos9.requirements.txt"
ENV APP_MAIN_DEPS \
    util-linux \
    python3 \
    python3-pip \
    python3-six \
    python3-dbus \
    python3-pexpect

WORKDIR /data

FROM base as install_main_deps

RUN dnf update -y && dnf install -y $APP_MAIN_DEPS && dnf clean all

FROM install_main_deps as install_dev_deps
RUN curl $URL_GET_PIP | $PYTHON
COPY $APP_DEV_DEPS $APP_DEV_DEPS
RUN $PIP install -r $APP_DEV_DEPS

FROM install_dev_deps as install_application
RUN groupadd --gid=1000 -r app && \
    useradd --uid=1000 --gid=1000 app
RUN chown -R app:app .
COPY --chown=app:app . .
USER app:app
