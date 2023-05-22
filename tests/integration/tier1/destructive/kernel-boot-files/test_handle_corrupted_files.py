import os
import re
import subprocess

import pytest

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS


INITRAMFS_FILE = "/boot/initramfs-%s.img"
BACKUP_INITRAMFS_FILE = "/boot/initramfs-%s.backup.img"


def get_latest_installed_kernel_version(kernel_name):
    """Utility function to get the latest installed kernel."""

    output = subprocess.check_output(["rpm", "-q", "--last", kernel_name]).decode()
    latest_installed_kernel = output.split("\n", maxsplit=1)[0].split(" ")[0]
    latest_installed_kernel = latest_installed_kernel.split("%s-" % kernel_name)[-1]
    return latest_installed_kernel.strip()


def corrupt_initramfs_file(shell, kernel_version):
    """Utility function to corrupt the initramfs file."""
    initramfs_file = INITRAMFS_FILE % kernel_version
    initramfs_backup = BACKUP_INITRAMFS_FILE % kernel_version

    # Assert that the file exists on the system
    assert os.path.exists(initramfs_file)

    # Copy the original file as a backup, so we can restore it later
    assert shell("cp %s %s" % (initramfs_file, initramfs_backup)).returncode == 0

    # Corrupt the file
    cmd = ["dd", "if=/dev/urandom", "bs=1024", "count=1", "of=%s" % initramfs_file]
    subprocess.run(cmd, check=False)


def restore_original_initramfs(shell, kernel_version):
    """Utility function to restore the initramfs after the conversion."""
    initramfs_file = INITRAMFS_FILE % kernel_version
    initramfs_backup = BACKUP_INITRAMFS_FILE % kernel_version

    # Assert that the original file still exists
    assert os.path.exists(initramfs_file)

    # Delete it as we will restore from the backup
    assert shell("rm -rf %s" % initramfs_file).returncode == 0

    # Move the backup to be the original one again
    assert shell("mv %s %s" % (initramfs_backup, initramfs_file)).returncode == 0

    # Assert that the file exists
    assert os.path.exists(initramfs_file)


@pytest.mark.test_handle_corrupted_initramfs_file
def test_corrupted_initramfs_file(convert2rhel, shell):
    """
    Verify, that an output with a warning message is sent to the user in case of a
    corrupted initramfs file.

    This case can happen when the transaction is run successfully, due to the lack of
    a disk space in the /boot partition, the kernel scriptlet will fail to copy
    the uncompressed initramfs file to /boot/initramfs-*.img, thus, leaving the
    file in a partial state and corrupted.

    Since this could be a real scenario, we prepared this test to assert that,
    if it happens, Convert2RHEL can detect that partial file there and instruct
    the user on how to fix the problem.

    .. note::
        @lnykryn made a reproducer for the `cp` issue that can be seen here:
        https://gist.github.com/r0x0d/5d6a93c5827bd365e934f3d612fdafae

        Since it would take very long to reproduce the `cp` issue as seen in
        the gist above, we are just corrupting the file to make the assertation
        correct. If the file has any data inside of it that is supposed to
        corrupt them, or, some partial data is missing, we will receive the
        same output from `lsinitrd`, therefore, it is easier to corrupt the
        data than removing random parts of it.
    """
    kernel_name = "kernel"
    if re.match(r"^(centos|oracle|alma|rocky)-8", SYSTEM_RELEASE_ENV):
        kernel_name = "kernel-core"

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        c2r.expect("Convert: List remaining non-Red Hat packages")

        kernel_version = get_latest_installed_kernel_version(kernel_name)

        # Corrupt the initramfs file to make the conversion to output steps on
        # how to fix the problem. We back up the original one before corrupting
        # it as we need to restore the file in order to properly finish the
        # tests.
        corrupt_initramfs_file(shell, kernel_version)

        assert c2r.expect("Couldn't verify initramfs file. It may be corrupted.") == 0
        assert c2r.expect("Output of lsinitrd") == 0
        assert c2r.expect("Couldn't verify the kernel boot files in the boot partition.") == 0

        # We have to restore the original initramfs file in order to use the
        # checks-after-conversion tests to assert that most of the conversion
        # is done properly.
        restore_original_initramfs(shell, kernel_version)

    assert c2r.exitstatus == 0
