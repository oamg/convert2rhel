FROM centos:8 as base

ENV PYTHON python3
ENV PIP pip3
ENV PYTHONDONTWRITEBYTECODE 1

ENV URL_GET_PIP "https://bootstrap.pypa.io/pip/3.6/get-pip.py"
ENV APP_DEV_DEPS "requirements/centos8.requirements.txt"
ENV APP_MAIN_DEPS \
    python3 \
    python3-six \
    python3-dbus \
    python3-pexpect

WORKDIR /data

FROM base as install_main_deps

RUN sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-Linux-* && \
    sed -i 's|#baseurl=http://mirror.centos.org|baseurl=https://vault.centos.org|g' /etc/yum.repos.d/CentOS-Linux-*

RUN dnf update -y && dnf install -y $APP_MAIN_DEPS && dnf clean all

FROM install_main_deps as install_dev_deps
RUN curl $URL_GET_PIP | $PYTHON
COPY $APP_DEV_DEPS $APP_DEV_DEPS
RUN $PIP install -r $APP_DEV_DEPS

FROM install_dev_deps as install_application
RUN groupadd --gid=1000 -r app && \
    useradd -r --uid=1000 --gid=1000 app
RUN chown -R app:app .
COPY --chown=app:app . .
USER app:app
