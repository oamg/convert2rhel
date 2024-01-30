FROM almalinux:9 as base

ENV PODMAN_USERNS=keep-id
ENV PYTHON python3
ENV PIP pip
ENV PYTHONDONTWRITEBYTECODE 1

ENV APP_DEV_DEPS "alma9/requirements.txt"
ENV APP_MAIN_DEPS \
    python3 \
    python3-pip \
    python3-six \
    python3-dbus \
    python3-pexpect \
    git \
    man \
    make

ENV USERNAME=vscode
ENV USER_UID=1000
ENV USER_GID=$USER_UID

WORKDIR /workspaces/convert2rhel

FROM base as install_main_deps

RUN dnf update -y && dnf install -y $APP_MAIN_DEPS && dnf clean all

FROM install_main_deps as install_dev_deps

COPY $APP_DEV_DEPS $APP_DEV_DEPS
RUN $PIP install -r $APP_DEV_DEPS

FROM install_dev_deps as install_application

RUN groupadd --gid=$USER_GID -r $USERNAME && \
    useradd --uid=$USER_UID --home /home/$USERNAME --gid=$USER_GID -m $USERNAME

RUN chown -R $USERNAME:$USERNAME .
COPY --chown=$USERNAME:$USERNAME . .

COPY alma9/.bashrc /home/$USERNAME
USER $USERNAME:$USERNAME
