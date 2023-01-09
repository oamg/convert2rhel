FROM centos:8 as base

ENV PODMAN_USERNS=keep-id
ENV PYTHON python3
ENV PIP pip3
ENV PYTHONDONTWRITEBYTECODE 1

ENV URL_GET_PIP "https://bootstrap.pypa.io/pip/3.6/get-pip.py"
ENV APP_DEV_DEPS ".devcontainer/centos8.requirements.txt"
ENV APP_MAIN_DEPS \
    python3 \
    python3-six \
    python3-dbus \
    python3-pexpect \
    git

ENV USERNAME=vscode
ENV USER_UID=1000
ENV USER_GID=$USER_UID

WORKDIR /workspaces/convert2rhel

FROM base as install_main_deps

RUN sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-Linux-* && \
    sed -i 's|#baseurl=http://mirror.centos.org|baseurl=https://vault.centos.org|g' /etc/yum.repos.d/CentOS-Linux-*

RUN dnf update -y && dnf install -y $APP_MAIN_DEPS && dnf clean all

FROM install_main_deps as install_dev_deps

RUN curl $URL_GET_PIP | $PYTHON
COPY $APP_DEV_DEPS $APP_DEV_DEPS
RUN $PIP install -r $APP_DEV_DEPS

FROM install_dev_deps as install_application

RUN groupadd --gid=$USER_GID -r $USERNAME && \
    useradd --uid=$USER_UID --home /home/$USERNAME --gid=$USER_GID -m $USERNAME

RUN chown -R $USERNAME:$USERNAME .
COPY --chown=$USERNAME:$USERNAME . .

COPY .devcontainer/.bashrc /home/$USERNAME
USER $USERNAME:$USERNAME
