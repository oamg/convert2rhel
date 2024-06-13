import os
import re

import pexpect.exceptions
import pytest

from conftest import SYSTEM_RELEASE_ENV, SystemInformationRelease


def _cross_vendor_kernel():
    """
    Helper function to assign a cross vendor kernel.
    Example:
        Running on CentOS 7, we install the Oracle Linux 7 signed kernel.
        distro == centos-7
        install_what = oracle-7-kernel
    """
    with open("/etc/yum.repos.d/stream9test.repo", "a") as repo:
        repo.write(f"[custom-kernel-repo]\n")
        repo.write(f"name=Repo to install the cross vendor kernel from\n")
        repo.write(f"baseurl=https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/os\n")
        repo.write("enabled=0\n")
        repo.write("gpgcheck=0\n")

    # This mapping includes cross vendor kernels and their respective grub substrings to set for boot
    install_what_kernel_mapping = {
        "oracle-7-kernel": {
            "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL7/latest/x86_64/getPackage/kernel-3.10.0-1160.76.1.0.1.el7.x86_64.rpm",
            "grub_substring": "CentOS Linux (3.10.0-1160.76.1.0.1.el7.x86_64) 7 (Core)",
        },
        "centos-7-kernel": {
            "custom_kernel": "http://vault.centos.org/centos/7/os/x86_64/Packages/kernel-3.10.0-1160.el7.x86_64.rpm",
            "grub_substring": "Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64",
        },
        "oracle-8-kernel": {
            "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/5/baseos/base/x86_64/getPackage/kernel-core-4.18.0-348.el8.x86_64.rpm",
            "grub_substring": "Oracle Linux Server (4.18.0-348.el8.x86_64) 8.5",
        },
        "centos-8-kernel": {
            "custom_kernel": "https://vault.centos.org/centos/8.5.2111/BaseOS/x86_64/os/Packages/kernel-core-4.18.0-348.7.1.el8_5.x86_64.rpm",
            "grub_substring": "CentOS Linux (4.18.0-348.7.1.el8_5.x86_64) 8",
        },
        "stream-9-kernel": {
            "custom_kernel": "https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/os/Packages/kernel-5.14.0-457.el9.x86_64.rpm",
            "grub_substring": "CentOS Stream (5.14.0-457.el9.x86_64.rpm) 9",
        },
        "alma-9-kernel": {
            "custom_kernel": "https://repo.almalinux.org/almalinux/9.4/BaseOS/x86_64/os/Packages/kernel-5.14.0-427.20.1.el9_4.x86_64.rpm",
            "grub_substring": "AlmaLinux (5.14.0-427.20.1.el9_4.x86_64) 9.4 (Seafoam Ocelot)",
        },
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

    custom_kernel, grub_substring = install_what_kernel_mapping[install_what].values()

    return custom_kernel, grub_substring


@pytest.fixture(scope="function")
def custom_kernel(shell, hybrid_rocky_image):
    """
    Fixture for test_custom_kernel.
    Install CentOS kernel on Oracle Linux and vice versa to mimic the custom
    kernel that is not signed by the running OS official vendor.
    Remove the current installed kernel and install the machine default kernel
    after the test.
    """
    custom_kernel, grub_substring = _cross_vendor_kernel()
    if os.environ["TMT_REBOOT_COUNT"] == "0":

        # We need to provide full repository for Stream 9 kernel installation
        # to satisfy the dependencies
        repo_opt = ""
        if "Stream" in grub_substring:
            repo_opt = "--enablerepo=custom-kernel-repo"

        assert shell(f"yum install {custom_kernel} -y {repo_opt}").returncode == 0

        assert shell(f"grub2-set-default '{grub_substring}'").returncode == 0

        shell("tmt-reboot -t 600")

    yield

    if os.environ["TMT_REBOOT_COUNT"] == "1":
        # Remove the current installed kernel and install the machine default kernel.
        custom_kernel_release = custom_kernel.rsplit("/", 1)[-1].replace(".rpm", "")
        assert shell("rpm -e %s" % custom_kernel_release).returncode == 0

        original_kernel = os.popen("rpm -q --last kernel | head -1 | cut -d ' ' -f1").read()
        original_kernel_release = original_kernel.rsplit("/")[-1].replace(".rpm", "").split("-")[-1]

        # Install back the CentOS 8.5 original kernel
        if "centos-8-latest" in SYSTEM_RELEASE_ENV:
            assert shell("yum install -y %s" % original_kernel).returncode == 0

        assert (
            shell(
                "grubby --set-default /boot/vmlinuz-*%s" % original_kernel_release,
            ).returncode
            == 0
        )
        shell("grub2-mkconfig -o /boot/grub2/grub.cfg")
        shell("rm -f /etc/yum.repos.d/stream9test.repo")
        # Reboot
        shell("tmt-reboot -t 600")


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
