import platform

import pytest


def test_install_one_kernel(shell):
    # installing kernel package
    assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
    # set deafault kernel
    if "centos-7" in platform.platform():
        assert shell("grub2-set-default 'CentOS Linux (3.10.0-1160.el7.x86_64) 7 (Core)'").returncode == 0
    elif "oracle-7" in platform.platform():
        assert shell("grub2-set-default 'Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64'").returncode == 0

    # replace url in yum.repos.d rhel repo
    original_url = "baseurl = http://rhsm-pulp.corp.redhat.com/content/dist/rhel/server/7/\$releasever/\$basearch/os/"
    new_url = "baseurl=http://rhsm-pulp.corp.redhat.com/content/dist/rhel/server/7/7.9/x86_64/os/"
    shell('sed -i "s+{}+{}+g" /etc/yum.repos.d/rhel7.repo'.format(original_url, new_url))
