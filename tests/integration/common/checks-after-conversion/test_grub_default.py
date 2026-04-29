import re

import pytest
from test_helpers.common_functions import log_file


@pytest.mark.test_grub_default
def test_grub_default(shell):
    """
    After conversion check.
    Verify that the default grub title matches RHEL.
    Additionally verify that the kernel the system is booted into
    the one defined in the default entry.
    """
    log_file("/boot/grub2/grub.cfg", "check_grub_default", "boot_grub2_grub.cfg", skip_nonexistent=True)
    log_file("/boot/grub2/grubenv", "check_grub_default", "boot_grub2_grubenv", skip_nonexistent=True)
    log_file("/etc/default/grub", "check_grub_default", "etc_default_grub", skip_nonexistent=True)
    grub_default = shell("grubby --default-title").output.strip()
    running_kernel = shell("uname -r").output.strip()
    title_rgx = f"Red Hat Enterprise Linux(?: Server)? \\({running_kernel}\\)"
    assert re.match(title_rgx, grub_default)
