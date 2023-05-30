import os
import re
import subprocess

import pytest

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


INITRAMFS_FILE = "/boot/initramfs-%s.img"
VMLINUZ_FILE = "/boot/vmlinuz-%s"


def get_latest_installed_kernel_version(kernel_name):
    """Utility function to get the latest installed kernel."""

    output = subprocess.check_output(["rpm", "-q", "--last", kernel_name]).decode()
    latest_installed_kernel = output.split("\n", maxsplit=1)[0].split(" ")[0]
    latest_installed_kernel = latest_installed_kernel.split("%s-" % kernel_name)[-1]
    return latest_installed_kernel.strip()


def remove_kernel_boot_files(shell, kernel_version):
    """Utility function to remove the RHEL kernel boot files."""

    initramfs_file = INITRAMFS_FILE % kernel_version
    vmlinuz_file = VMLINUZ_FILE % kernel_version

    # Assert that we have the files in the /boot/ folder
    assert os.path.exists(initramfs_file)
    assert os.path.exists(vmlinuz_file)

    # Remove the installed RHEL kernel boot files, simulating that they failed to be generated during the conversion
    assert shell("rm -f %s" % initramfs_file).returncode == 0
    assert shell("rm -f %s" % vmlinuz_file).returncode == 0


@pytest.mark.missing_kernel_boot_files
def test_missing_kernel_boot_files(convert2rhel, shell):
    """
    Verify if an output with a warning message is sent to the user in case of
    the tool can't detect the initramfs and vmlinuz files in /boot.

    This case can happen if the kernel scriptlet fails during the yum/dnf
    transaction where Convert2RHEL tries to replace the packages. Even though
    the scriptlet can fail, the transaction will still continue and the
    workflow will continue to be executed. The problem is that, with a
    scriptlet failure when replacing/installing a kernel, the initramfs and
    vmlinuz may not be available in the /boot partition, especially if there
    isn't sufficient disk space available in there. This test has the intention
    to verify that the warning with the correct steps are provided to the
    user in order to overcome this case and fix it for them.
    """

    kernel_name = "kernel"
    if re.match(r"^(centos|oracle|alma|rocky)-8(\.\d|-latest)$", SYSTEM_RELEASE_ENV):
        kernel_name = "kernel-core"

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_SCA_USERNAME"),
            env.str("RHSM_SCA_PASSWORD"),
        )
    ) as c2r:
        c2r.expect("Convert: List remaining non-Red Hat packages")

        kernel_version = get_latest_installed_kernel_version(kernel_name)

        # We want to simulate with this test that when we don't detect the
        # initramfs and vmlinuz files, we will produce a warning and tell the
        # user what to do in order to fix the problem. To not cause any more
        # mess other than what we want, let's just remove the two file from the
        # system, and see if Convert2RHEL will detect that the right way.
        remove_kernel_boot_files(shell, kernel_version)

        assert c2r.expect("Couldn't verify the kernel boot files in the boot partition.") == 0

        # We have to restore the boot files in order to use the checks-after-conversion tests to
        # assert that the rest of the conversion has succeeded.
        # We'll do that the same way we're telling the user in a warning message how to fix the problem.
        # That is by reinstalling the RHEL kernel and re-running grub2-mkconfig.
        assert shell("yum reinstall {}-{} -y".format(kernel_name, kernel_version)).returncode == 0
        assert shell("grub2-mkconfig -o /boot/grub2/grub.cfg").returncode == 0

    assert c2r.exitstatus == 0
