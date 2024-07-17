FROM centos:7 as base

ENV PODMAN_USERNS=keep-id
ENV PYTHON python2
ENV PIP pip
ENV PYTHONDONTWRITEBYTECODE 1

ENV URL_GET_PIP "https://bootstrap.pypa.io/pip/2.7/get-pip.py"
ENV APP_DEV_DEPS "centos7/requirements.txt"
ENV APP_MAIN_DEPS \
    python2 \
    python-six \
    dbus-python \
    pexpect \
    git

ENV USERNAME=vscode
ENV USER_UID=1000
ENV USER_GID=$USER_UID

WORKDIR /workspaces/convert2rhel

FROM base as install_main_deps

RUN sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-* && \
    sed -i 's|#baseurl=http://mirror.centos.org|baseurl=https://vault.centos.org|g' /etc/yum.repos.d/CentOS-*

RUN yum update -y && yum install -y $APP_MAIN_DEPS && yum clean all

FROM install_main_deps as install_dev_deps
COPY $APP_DEV_DEPS $APP_DEV_DEPS
RUN curl $URL_GET_PIP | $PYTHON
RUN $PIP install -r $APP_DEV_DEPS

FROM install_dev_deps as install_application

RUN groupadd --gid=$USER_GID -r $USERNAME && \
    useradd --uid=$USER_UID --home /home/$USERNAME --gid=$USER_GID -m $USERNAME

RUN chown -R $USERNAME:$USERNAME .
COPY --chown=$USERNAME:$USERNAME . .

COPY centos7/.bashrc /home/$USERNAME
USER $USERNAME:$USERNAME
