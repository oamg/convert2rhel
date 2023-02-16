import os
import shlex
import subprocess

from multiprocessing import Pool

import pytest

from envparse import env


def get_latest_installed_kernel(kernel_name):
    """Utility function to get the latest installed kernel."""

    output = subprocess.check_output(["rpm", "-q", "--last", kernel_name])
    latest_installed_kernel = output.split("\n", maxsplit=1)[0].split(" ")[0]
    latest_installed_kernel = latest_installed_kernel.split("%s-" % kernel_name)[-1]
    return latest_installed_kernel.strip()


def corrupt_initramfs_file(kernel_name):
    """Utility function to corrupt the initramfs file."""
    latest_installed_kernel = get_latest_installed_kernel(kernel_name)

    while True:
        if os.path.exists("/boot/initramfs-%s.img" % latest_installed_kernel):
            cmd = "dd if=/dev/urandom bs=1024 count=1 of=/boot/initramfs-%s.img" % latest_installed_kernel
            subprocess.run(shlex.split(shlex.quote(cmd)), shell=True, check=True)
            print("Done! initramfs file is corrupted.")
            return True


@pytest.mark.corrupted_initramfs_file
def test_corrupted_initramfs_file(system_release, convert2rhel):
    """
    Verify if an output with a warning message is sent to the user in case of a
    corrupted initramfs file.

    This case can happen when the transaction ran successfully, but, for lack of
    disk space in the /boot partition, the kernel scriptlet will fail to copy
    the uncompressed initramfs file to /boot/initramfs-*.img, thus, leaving the
    file in an partial state and corrupted.

    Since this could be a real scenario, we prepared this test to assert that,
    if it happens, Convert2RHEL can detect that partial file there and instruct
    the user on how to fix the problem.

    .. note::
        @lnykryn made an reproducer for the `cp` issue that can be seen here: https://gist.github.com/r0x0d/5d6a93c5827bd365e934f3d612fdafae
    """
    kernel_name = "kernel"
    if "centos-8" in system_release or "oracle-8" in system_release:
        kernel_name = "kernel-core"

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        # Start the watcher as soon as we hit this message.
        c2r.expect("Convert: List remaining non-Red Hat packages") == 0

        with Pool(processes=1) as pool:
            _ = pool.apply_async(corrupt_initramfs_file, (kernel_name,))

        assert c2r.expect("Output of lsinitrd") == 0
        assert c2r.expect("Couldn't verify the kernel boot files in the boot partition.") == 0

    assert c2r.exitstatus == 0
