import os
import re

import pexpect.exceptions
import pytest

from conftest import SYSTEM_RELEASE_ENV, SystemInformationRelease, _get_full_kernel_title, grub_setup_workaround


def _cross_vendor_kernel():
    """
    Helper function to assign a cross vendor kernel.
    Example:
        Running on CentOS 7, we install the Oracle Linux 7 signed kernel.
        distro == centos-7
        install_what = oracle-7-kernel
    """
    # This mapping includes cross vendor kernels and their respective grub substrings to set for boot
    install_what_kernel_mapping = {
        "oracle-7-kernel": "https://yum.oracle.com/repo/OracleLinux/OL7/latest/x86_64/",
        "centos-7-kernel": "http://vault.centos.org/centos/7/os/x86_64/",
        "oracle-8-kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/5/baseos/base/x86_64/",
        "centos-8-kernel": "https://vault.centos.org/centos/8.5.2111/BaseOS/x86_64/os/",
        "stream-9-kernel": "https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/os/",
        "alma-9-kernel": "https://repo.almalinux.org/almalinux/9.4/BaseOS/x86_64/os/",
    }

    distro = f"{SystemInformationRelease.distribution}-{SystemInformationRelease.version.major}"

    install_what = ""
    # Based on a current OS we decide which cross vendor kernel to install
    # install_what variable indicates that
    if distro == "oracle-7":
        install_what = "centos-7-kernel"
    elif distro == "centos-7":
        install_what = "oracle-7-kernel"
    elif re.match(r"^(almalinux|rocky|centos|stream)-8", distro):
        install_what = "oracle-8-kernel"
    elif distro == "oracle-8":
        install_what = "centos-8-kernel"
    elif re.match(r"^(almalinux|rocky|centos|oracle)-9", distro):
        install_what = "stream-9-kernel"
    elif distro == "stream-9":
        install_what = "alma-9-kernel"

    repo_from_path = install_what_kernel_mapping.get(install_what)

    return repo_from_path


@pytest.fixture(scope="function")
def custom_kernel(shell, hybrid_rocky_image):
    """
    Fixture for test_custom_kernel.
    Install CentOS kernel on Oracle Linux and vice versa to mimic the custom
    kernel that is not signed by the running OS official vendor.
    Remove the current installed kernel and install the machine default kernel
    after the test.
    """
    repo_from_path = _cross_vendor_kernel()
    custom_kernel_installed = None
    if os.environ["TMT_REBOOT_COUNT"] == "0":
        # Install the kernel from the path provided by the _cross_vendor_kernel
        # This way we don't rely on any specific version of kernel hardcoded and install what's available in the repository
        # Disable all other repositories
        # Call without the gpg check, so we won't need to import the GPG key
        assert (
            shell(
                f"yum install kernel -y --nogpgcheck --disablerepo=* --repofrompath=customkernelrepo,{repo_from_path}"
            ).returncode
            == 0
        )
        # Read the last installed kernel version from the rpm command output
        custom_kernel_installed = os.popen("rpm -q --last kernel | head -1 | cut -d ' ' -f1").read().strip()

        # Assemble the full title of the custom kernel and set it as default to boot to
        grub_substring = _get_full_kernel_title(shell, kernel=custom_kernel_installed.replace("kernel-", ""))
        assert shell(f"grub2-set-default '{grub_substring}'").returncode == 0
        shell("tmt-reboot -t 600")

    yield

    if os.environ["TMT_REBOOT_COUNT"] == "1":
        # This is kind of naive, but we assume the second latest installed kernel is the original one
        # We use head to filter the first two lines of the output and tail to filter the bottom line
        original_kernel = os.popen("rpm -q --last kernel | head -2 | tail -1 | cut -d ' ' -f1").read().strip()
        original_kernel_title = _get_full_kernel_title(shell, kernel=original_kernel.replace("kernel-", ""))
        # Install back the CentOS 8.5 original kernel
        if "centos-8-latest" in SYSTEM_RELEASE_ENV:
            assert shell(f"yum reinstall -y kernel").returncode == 0

        grub_setup_workaround(shell)
        assert shell(f"grub2-set-default '{original_kernel_title}'").returncode == 0
        shell("grub2-mkconfig -o /boot/grub2/grub.cfg")
        # Reboot
        shell("tmt-reboot -t 600")

    if os.environ["TMT_REBOOT_COUNT"] == "2":
        custom_kernel_installed = os.popen("rpm -q --last kernel | head -1 | cut -d ' ' -f1").read().strip()
        # After the system has the original kernel running, remove the custom kernel
        kernel_to_remove = custom_kernel_installed.replace("kernel", "kernel*")
        assert shell(f"yum remove -y {kernel_to_remove}").returncode == 0


def test_custom_kernel(convert2rhel, shell, custom_kernel):
    """
    Run the conversion with custom kernel installed on the system.
    """
    os_vendor = "CentOS"
    if "oracle" in SYSTEM_RELEASE_ENV:
        os_vendor = "Oracle"
    elif "alma" in SYSTEM_RELEASE_ENV:
        os_vendor = "AlmaLinux"
    elif "rocky" in SYSTEM_RELEASE_ENV:
        os_vendor = "Rocky"

    if os.environ["TMT_REBOOT_COUNT"] == "1":
        try:
            with convert2rhel("--debug") as c2r:
                # We need to get past the data collection acknowledgement.
                c2r.expect("Continue with the system conversion?")
                c2r.sendline("y")

                c2r.expect(
                    "WARNING - Custom kernel detected. The booted kernel needs to be signed by {}".format(os_vendor)
                )
                c2r.expect_exact("RHEL_COMPATIBLE_KERNEL::INVALID_KERNEL_PACKAGE_SIGNATURE")

                c2r.sendcontrol("c")

            assert c2r.exitstatus == 1
        except (AssertionError, pexpect.exceptions.EOF, pexpect.exceptions.TIMEOUT) as e:
            print(f"There was an error: \n{e}")
            shell("tmt-report-result /tests/integration/tier0/non-destructive/kernel/custom_kernel FAIL")
            raise
