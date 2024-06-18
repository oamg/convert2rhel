import pytest


@pytest.mark.test_grub_default
def test_grub_default(shell):
    """
    After conversion check.
    Verify that the default grub title matches RHEL.
    Additionally verify that the kernel the system is booted into
    equals to the one defined in the default entry.
    """
    grub_default = shell("grubby --default-title").output.strip()
    running_kernel = shell("uname -r").output.strip()
    assert f"Red Hat Enterprise Linux ({running_kernel})" in grub_default