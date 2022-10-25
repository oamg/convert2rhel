FROM centos:6 as base

ENV PYTHON python2
ENV PIP pip2
ENV PYTHONDONTWRITEBYTECODE 1

ENV URL_GET_PIP "https://fedora-archive.ip-connect.vn.ua/epel/6/x86_64/Packages/p/python-pip-7.1.0-2.el6.noarch.rpm"
ENV APP_DEV_DEPS "requirements/centos6.requirements.txt"
ENV APP_PRE_DEV_DEPS "requirements/centos6_pre.requirements.txt"
ENV PREP_PIP_DEPS "scripts/centos6_pip_prep.sh"
ENV APP_MAIN_DEPS \
    python-six \
    pexpect \
    dbus-python \
    gcc \
    python-devel

WORKDIR /data

FROM base as install_main_deps
RUN sed -i 's/^mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-Base.repo &&\
    sed -i 's/^#baseurl.*$/baseurl=https:\/\/vault.centos.org\/6.10\/os\/x86_64/g' \
    /etc/yum.repos.d/CentOS-Base.repo
RUN yum update -y && yum install -y $APP_MAIN_DEPS && yum clean all

FROM install_main_deps as install_dev_deps
RUN yum install -y $URL_GET_PIP
COPY $PREP_PIP_DEPS $PREP_PIP_DEPS
COPY $APP_DEV_DEPS $APP_DEV_DEPS
COPY $APP_PRE_DEV_DEPS $APP_PRE_DEV_DEPS
RUN chmod +x $PREP_PIP_DEPS
# The SSL implementation that python-2.6 uses is insecure and pip refuses to install
# packages using it. This script will use curl to download the packages securely and
# then pip can be asked to install from the local files
RUN $PREP_PIP_DEPS
RUN $PIP install --no-index --find-links /data -r $APP_PRE_DEV_DEPS
RUN $PIP install --no-index --find-links /data -r $APP_DEV_DEPS

FROM install_dev_deps as install_application
RUN groupadd --gid=1000 -r app && \
    useradd -r --uid=1000 --gid=1000 app
RUN chown -R app:app .
COPY --chown=app:app . .
USER app:app
