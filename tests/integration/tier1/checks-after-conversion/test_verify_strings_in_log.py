import pytest


@pytest.mark.initramfs_and_vmlinuz_present
def test_verify_initramfs_and_vmlinuz_present(log_file_data):
    """
    Verify that after successful conversion the kernel boot files are
    present.

    Our criteria, in this case, is related to the `check_kernel_boot_files()`
    finding the two necessary boot files (initramfs and vmlinuz),
    and validating that the initramfs file is not corrupted.
    """
    assert "The initramfs and vmlinuz files are valid." in log_file_data
