import os

import pytest


def prepare_unbreakable_kernel(shell):
    """
    Helper function.
    Install unbreakable kernel and reboot using the tmt-reboot.
    """
    assert shell("yum install -y kernel-uek").returncode == 0
    kernel_version = shell("rpm -q --last kernel-uek | head -1 | cut -d ' ' -f1 | sed 's/kernel-uek-//'").output
    assert shell(f"grubby --set-default /boot/vmlinuz-{kernel_version}").returncode == 0
    shell("tmt-reboot -t 600")


def teardown_uek(shell):
    """
    Helper function.
    Install supported kernel back.
    """
    shell(
        "grubby --set-default /boot/vmlinuz-`rpm -q --qf '%{BUILDTIME}\t%{EVR}.%{ARCH}\n' kernel | sort -nr | head -1 | cut -f2`"
    )
    shell("tmt-reboot -t 600")


@pytest.mark.unsupported_kernel
def test_bad_conversion(shell, convert2rhel):
    """
    Verify that the check for compatible kernel on Oracle Linux works.
    Install unsupported kernel and run the conversion.
    Expect the warning message and c2r unsuccessful exit.
    """
    if os.environ["TMT_REBOOT_COUNT"] == "0":
        prepare_unbreakable_kernel(shell)
    elif os.environ["TMT_REBOOT_COUNT"] == "1":
        with convert2rhel("-y --no-rpm-va --debug", unregister=True) as c2r:
            c2r.expect("The booted kernel version is incompatible", timeout=600)
        assert c2r.exitstatus == 1
        # Clean up
        teardown_uek(shell)
