import platform

import pytest


def test_install_one_kernel(shell):
    # installing kernel package
    assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
    # set deafault kernel
    if platform.platform().find("centos-7") != -1:
        assert shell("grub2-set-default 'CentOS Linux (3.10.0-1160.el7.x86_64) 7 (Core)'").returncode == 0
    elif platform.platform().find("oracle-7") != -1:
        assert shell("grub2-set-default 'Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64'").returncode == 0

    # replace url in yum.repos.d rhel repo
    original_url = "baseurl=http://rhsm-pulp.corp.redhat.com/content/dist/rhel/server/7/7Server/x86_64/os/"
    new_url = "baseurl=http://download.englab.brq.redhat.com/released/rhel-7/RHEL-7/7.9/Server/x86_64/os/"
    shell('sed -i "s+{}+{}+g" /etc/yum.repos.d/rhel-7-internal.repo'.format(original_url, new_url))
