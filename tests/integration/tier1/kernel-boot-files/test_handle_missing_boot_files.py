import os
import shlex
import subprocess

from multiprocessing import Pool

import pytest

from envparse import env


def get_booted_kernel_version():
    """Utility function to get the booted kernel version."""
    kernel_version = subprocess.check_output(["uname", "-r"])
    return kernel_version.decode("utf-8").strip()


def fill_disk_space():
    """
    Utility function to fill-up disk space when a certain file is not present anymore.
    """
    kernel_version = get_booted_kernel_version()

    while True:
        if not os.path.exists("/boot/initramfs-%s.img" % kernel_version):
            cmd = "yes `dd if=/dev/urandom count=1 bs=1M|base64` > /boot/test"
            process = subprocess.run(
                shlex.split(cmd), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True
            )
            if "No space left" in process.stdout.decode():
                print("Done! The disk is now out of space.")
                return True


@pytest.mark.missing_kernel_boot_files
def test_missing_kernel_boot_files(convert2rhel):
    """
    Verify if an output with a warning message is sent to the user in case of
    the tool can't detect the initramfs and vmlinuz files in /boot.

    This case can happen if the kernel scriptlet fails during the yum/dnf
    transaction where Convert2RHEL tries to replace the packages. Even thought
    the scriptlet can fail, the transaction will still continue and the
    workflow will continue to be executed. The problem is that, with a
    scriptlet failure when replacing/installing a kernel, the initramfs and
    vmlinuz could not be available in the /boot partition, especially if there
    is no sufficient disk space available in there. This test has the intention
    to verify that the a warning with the correct steps are provided to the
    user in order to overcome this case and fix it for them.
    """

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Convert: Replace system packages", timeout=600) == 0
        with Pool(processes=1) as pool:
            _ = pool.apply_async(fill_disk_space, ())
        assert c2r.expect("Couldn't verify the kernel boot files in the boot partition.") == 0

    assert c2r.exitstatus == 0
