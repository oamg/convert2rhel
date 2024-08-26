import re

import pytest


@pytest.mark.test_grub_default
def test_grub_default(shell):
    """
    After conversion check.
    Verify that the default grub title matches RHEL.
    Additionally verify that the kernel the system is booted into
    the one defined in the default entry.
    """
    grub_default = shell("grubby --default-title").output.strip()
    running_kernel = shell("uname -r").output.strip()
    title_rgx = f"Red Hat Enterprise Linux(?: Server)? \\({running_kernel}\\)"
    assert re.match(title_rgx, grub_default)
