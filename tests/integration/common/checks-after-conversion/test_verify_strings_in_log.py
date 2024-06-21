import re


def test_verify_initramfs_and_vmlinuz_present(log_file_data):
    """
    Verify that after a successful conversion the kernel boot files are
    present.

    Our criteria, in this case, are related to the `check_kernel_boot_files()`
    finding the two necessary boot files (initramfs and vmlinuz),
    and validating that the initramfs file is not corrupted.
    """
    assert "The initramfs and vmlinuz files are valid." in log_file_data


def test_failed_to_parse_package_info_empty_arch_not_present(log_file_data):
    """
    Verify that in case of package with the `arch` field missing in its information,
    the message Failed to parse a package does not appear during the conversion run.
    """

    failed_to_parse = r"Failed to parse a package: Invalid package string - .+\.\(none\)"
    match = re.search(failed_to_parse, log_file_data)
    assert match is None, f"{failed_to_parse} is present in the log file data."


def test_traceback_not_present(log_file_data):
    """
    Verify that there is not a traceback raised in the log file during the conversion run.
    """
    traceback_str = r"traceback"
    match = re.search(traceback_str, log_file_data, re.IGNORECASE)
    assert match is None, "Traceback found in the log file data."
