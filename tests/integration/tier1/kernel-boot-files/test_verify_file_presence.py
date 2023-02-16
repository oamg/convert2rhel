import pytest

from envparse import env


@pytest.mark.check_boot_files_presence
def test_check_boot_files_presence(convert2rhel):
    """
    Verify that the conversion was successfull and the kernel boot files are
    present.

    Our criteria of a successfull conversion, in this case, is related to the
    `check_kernel_boot_files()` finding the two necessary boot files (initramfs
    and vmlinuz), and validating that the initramfs file is not corrupted.
    """

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        assert c2r.expect("Checking if vmlinuz file exists on the system.") == 0
        assert c2r.expect("Checking if initiramfs file exists on the system.") == 0
        assert c2r.expect("Initramfs and vmlinuz files exists and are valid.") == 0

    assert c2r.exitstatus == 0
