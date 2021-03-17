FROM centos:6 as base

ENV PYTHON python2
ENV PIP pip2
ENV PYTHONDONTWRITEBYTECODE 1

ENV URL_GET_PIP "https://bootstrap.pypa.io/pip/2.6/get-pip.py"
ENV APP_DEV_DEPS "requirements/centos6.requirements.txt"
ENV APP_MAIN_DEPS \
    python-six \
    pexpect

WORKDIR /data

FROM base as install_main_deps
RUN sed -i 's/^mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-Base.repo &&\
    sed -i 's/^#baseurl.*$/baseurl=https:\/\/vault.centos.org\/6.10\/os\/x86_64/g' \
    /etc/yum.repos.d/CentOS-Base.repo
RUN yum update -y && yum install -y $APP_MAIN_DEPS && yum clean all

FROM install_main_deps as install_dev_deps
RUN curl $URL_GET_PIP | $PYTHON
COPY $APP_DEV_DEPS $APP_DEV_DEPS
RUN $PIP install -r $APP_DEV_DEPS

FROM install_dev_deps as install_application
RUN groupadd --gid=1000 -r app && \
    useradd -r --uid=1000 --gid=1000 app
RUN chown -R app:app .
COPY --chown=app:app . .
#USER app:app
