import os

import pexpect.exceptions
import pytest

from conftest import SYSTEM_RELEASE_ENV


ORIGINAL_KERNEL = os.popen("rpm -q --last kernel | head -1 | cut -d ' ' -f1").read()

DISTRO_KERNEL_MAPPING = {
    "centos-7": {
        "original_kernel": ORIGINAL_KERNEL,
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL7/latest/x86_64/getPackage/kernel-3.10.0-1160.76.1.0.1.el7.x86_64.rpm",
        "grub_substring": "CentOS Linux (3.10.0-1160.76.1.0.1.el7.x86_64) 7 (Core)",
    },
    # We hardcode original kernel for CentOS 8.5 as it won't receive any updates anymore
    "centos-8-latest": {
        "original_kernel": "kernel-core-4.18.0-348.7.1.el8_5.x86_64",
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/5/baseos/base/x86_64/getPackage/kernel-core-4.18.0-348.el8.x86_64.rpm",
        "grub_substring": "Oracle Linux Server (4.18.0-348.el8.x86_64) 8.5",
    },
    "oracle-7": {
        "original_kernel": ORIGINAL_KERNEL,
        "custom_kernel": "http://vault.centos.org/centos/7/os/x86_64/Packages/kernel-3.10.0-1160.el7.x86_64.rpm",
        "grub_substring": "Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64",
    },
    # Install CentOS 8.5 kernel
    "oracle-8-latest": {
        "original_kernel": ORIGINAL_KERNEL,
        "custom_kernel": "https://vault.centos.org/centos/8.5.2111/BaseOS/x86_64/os/Packages/kernel-core-4.18.0-348.7.1.el8_5.x86_64.rpm",
        "grub_substring": "CentOS Linux (4.18.0-348.7.1.el8_5.x86_64) 8",
    },
    "alma-8": {
        "original_kernel": ORIGINAL_KERNEL,
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/5/baseos/base/x86_64/getPackage/kernel-core-4.18.0-348.el8.x86_64.rpm",
        "grub_substring": "Oracle Linux Server (4.18.0-348.el8.x86_64) 8.5",
    },
    "rocky-8": {
        "original_kernel": ORIGINAL_KERNEL,
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/5/baseos/base/x86_64/getPackage/kernel-core-4.18.0-348.el8.x86_64.rpm",
        "grub_substring": "Oracle Linux Server (4.18.0-348.el8.x86_64) 8.5",
    },
    "stream-8-latest": {
        "original_kernel": ORIGINAL_KERNEL,
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/5/baseos/base/x86_64/getPackage/kernel-core-4.18.0-348.el8.x86_64.rpm",
        "grub_substring": "Oracle Linux Server (4.18.0-348.el8.x86_64) 8.5",
    },
}

if "alma-8" in SYSTEM_RELEASE_ENV:
    distro = "alma-8"
elif "rocky" in SYSTEM_RELEASE_ENV:
    distro = "rocky-8"
else:
    distro = SYSTEM_RELEASE_ENV

_, CUSTOM_KERNEL, GRUB_SUBSTRING = DISTRO_KERNEL_MAPPING[distro].values()


@pytest.fixture(scope="function")
def custom_kernel(shell, hybrid_rocky_image):
    """
    Fixture for test_custom_kernel.
    Install CentOS kernel on Oracle Linux and vice versa to mimic the custom
    kernel that is not signed by the running OS official vendor.
    Remove the current installed kernel and install the machine default kernel
    after the test.
    """
    if os.environ["TMT_REBOOT_COUNT"] == "0":

        assert shell("yum install %s -y" % CUSTOM_KERNEL).returncode == 0

        assert shell("grub2-set-default '%s'" % GRUB_SUBSTRING).returncode == 0

        shell("tmt-reboot -t 600")

    yield

    if os.environ["TMT_REBOOT_COUNT"] == "1":
        # Remove the current installed kernel and install the machine default kernel.
        custom_kernel_release = CUSTOM_KERNEL.rsplit("/", 1)[-1].replace(".rpm", "")
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
        # Reboot
        shell("tmt-reboot -t 600")


@pytest.mark.test_custom_kernel
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
