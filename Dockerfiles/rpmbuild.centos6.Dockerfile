FROM centos:6 as base

RUN sed -i 's/^mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-Base.repo &&\
    sed -i 's/^#baseurl.*$/baseurl=https:\/\/vault.centos.org\/6.10\/os\/x86_64/g' \
    /etc/yum.repos.d/CentOS-Base.repo
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
ENTRYPOINT ["scripts/build_locally.sh"]
