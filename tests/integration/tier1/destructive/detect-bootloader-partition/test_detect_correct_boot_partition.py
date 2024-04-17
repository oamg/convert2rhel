import platform
import subprocess

import pytest

from conftest import TEST_VARS


EFI_BOOT_MOUNTPOINT = "/boot/efi"
SYSTEM_RELEASE = platform.platform()

# TODO(danmyway): We need to include another test case in this to verify that
# Convert2RHEL can detect the correct partition even though it will not be in
# the usual /dev/xxx1. We are holding https://github.com/teemtee/tmt/pull/1835
# to get merged, as well, UEFI support in testing farm to create such case.


def get_boot_device():
    """Utility function to get the device that the `EFI_BOOT_MOUNTPOINT` lives in."""
    device = subprocess.check_output(["grub2-probe", "--target=device", EFI_BOOT_MOUNTPOINT])
    return device.decode().strip()


def get_device_name(device):
    """Utility function to get a device name only, without the partition number."""
    name = subprocess.check_output(["lsblk", "-spnlo", "name", device])
    return name.decode().strip().splitlines()[-1].strip()


def get_device_partition(device):
    """Utility function to retrieve the boot partition for a given device."""
    partition = subprocess.check_output(["blkid", "-p", "-s", "PART_ENTRY_NUMBER", device])
    partition = partition.decode().strip()
    return partition.rsplit("PART_ENTRY_NUMBER=", maxsplit=1)[-1].replace('"', "")


@pytest.mark.test_detect_correct_boot_partition
def test_detect_correct_boot_partition(convert2rhel):
    """
    Verify that the correct arguments for disk and partition will be used
    during the creation of a new EFI partition.

    This test does a series of assertions to verify that Convert2RHEl was able
    to correctly detect the EFI boot partition during the execution, no matter
    what disk/partition the EFI mount will be.
    """
    boot_device = get_boot_device()
    boot_device_name = get_device_name(boot_device)
    boot_partition = get_device_partition(boot_device)

    rhel_version = "8"

    if "centos-7" in SYSTEM_RELEASE or "oracle-7" in SYSTEM_RELEASE:
        rhel_version = "7"

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        assert c2r.expect("Calling command '/usr/sbin/blkid -p -s PART_ENTRY_NUMBER %s'" % boot_device) == 0

        # This assertion should always match what comes from boot_partition.
        assert c2r.expect("Block device: %s" % boot_device_name) == 0
        assert c2r.expect("ESP device number: %s" % boot_partition) == 0

        assert c2r.expect("Adding 'Red Hat Enterprise Linux %s' UEFI bootloader entry." % rhel_version) == 0

        # Only asserting half of the command as we care mostly about the
        # `--disk` and `--part`.
        assert (
            c2r.expect(
                "Calling command '/usr/sbin/efibootmgr --create --disk %s --part %s"
                % (boot_device_name, boot_partition)
            )
            == 0
        )

    assert c2r.exitstatus == 0
