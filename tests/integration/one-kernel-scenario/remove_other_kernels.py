import pytest


def test_remove_other_kernels(shell):
    # remove all kernels except the kernel-3.10.0-1160.el7.x86_64
    assert shell("rpm -qa kernel | grep -v 'kernel-3.10.0-1160.el7.x86_64' | xargs yum -y remove")
    assert shell("rpm -qa kernel | wc -l").output == "1\n"
