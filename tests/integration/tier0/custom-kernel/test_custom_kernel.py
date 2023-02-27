import os

import pytest

from conftest import SYSTEM_RELEASE_ENV


ORIGINAL_KERNEL = os.popen("rpm -q --last kernel | head -1 | cut -d ' ' -f1").read()

DISTRO_KERNEL_MAPPING = {
    "centos-7": {
        "original_kernel": f"{ORIGINAL_KERNEL}",
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL7/latest/x86_64/getPackage/kernel-3.10.0-1160.76.1.0.1.el7.x86_64.rpm",
        "grub_substring": "CentOS Linux (3.10.0-1160.76.1.0.1.el7.x86_64) 7 (Core)",
    },
    # We hardcode original kernel for both CentOS 8.4 and CentOS 8.5 as it won't receive any updates anymore
    "centos-8.4": {
        "original_kernel": "kernel-core-4.18.0-305.25.1.el8_4.x86_64",
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/4/baseos/base/x86_64/getPackage/kernel-core-4.18.0-305.el8.x86_64.rpm",
        "grub_substring": "Oracle Linux Server (4.18.0-305.el8.x86_64) 8.4",
    },
    "centos-8.5": {
        "original_kernel": "kernel-core-4.18.0-348.7.1.el8_5.x86_64",
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/5/baseos/base/x86_64/getPackage/kernel-core-4.18.0-348.el8.x86_64.rpm",
        "grub_substring": "Oracle Linux Server (4.18.0-348.el8.x86_64) 8.5",
    },
    "oracle-7": {
        "original_kernel": f"{ORIGINAL_KERNEL}",
        "custom_kernel": "http://mirror.centos.org/centos/7/os/x86_64/Packages/kernel-3.10.0-1160.el7.x86_64.rpm",
        "grub_substring": "Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64",
    },
    # Install CentOS 8.5 kernel
    "oracle-8.7": {
        "original_kernel": f"{ORIGINAL_KERNEL}",
        "custom_kernel": "https://vault.centos.org/centos/8.5.2111/BaseOS/x86_64/os/Packages/kernel-core-4.18.0-348.7.1.el8_5.x86_64.rpm",
        "grub_substring": "CentOS Linux (4.18.0-348.7.1.el8_5.x86_64) 8",
    },
}

_, CUSTOM_KERNEL, GRUB_SUBSTRING = DISTRO_KERNEL_MAPPING[SYSTEM_RELEASE_ENV].values()


def install_custom_kernel(shell):
    """
    Install CentOS kernel on Oracle Linux and vice versa to mimic the custom
    kernel that is not signed by the running OS official vendor.
    """

    assert shell("yum install %s -y" % CUSTOM_KERNEL).returncode == 0

    assert shell("grub2-set-default '%s'" % GRUB_SUBSTRING).returncode == 0

    shell("tmt-reboot -t 600")


def clean_up_custom_kernel(shell):
    """
    Remove the current installed kernel and install the machine default kernel.
    """
    custom_kernel_release = CUSTOM_KERNEL.rsplit("/")[-1].replace(".rpm", "")
    assert shell("rpm -e %s" % custom_kernel_release).returncode == 0

    original_kernel = os.popen("rpm -q --last kernel | head -1 | cut -d ' ' -f1").read()
    original_kernel_release = original_kernel.rsplit("/")[-1].replace(".rpm", "").split("-")[-1]

    # Install back the CentOS 8.5 original kernel
    if "centos-8.5" in SYSTEM_RELEASE_ENV:
        assert shell("yum install -y %s" % original_kernel).returncode == 0

    assert (
        shell(
            "grubby --set-default /boot/vmlinuz-*%s" % original_kernel_release,
        ).returncode
        == 0
    )


@pytest.mark.test_custom_kernel
def test_custom_kernel(convert2rhel, shell):
    """
    Run the conversion with custom kernel installed on the system.
    """
    os_vendor = "CentOS"
    if "oracle" in SYSTEM_RELEASE_ENV:
        os_vendor = "Oracle"

    if os.environ["TMT_REBOOT_COUNT"] == "0":
        install_custom_kernel(shell)
    elif os.environ["TMT_REBOOT_COUNT"] == "1":
        with convert2rhel("--no-rpm-va --debug") as c2r:
            # We need to get past the data collection acknowledgement.
            c2r.expect("Continue with the system conversion?")
            c2r.sendline("y")

            c2r.expect("WARNING - Custom kernel detected. The booted kernel needs to be signed by {}".format(os_vendor))
            c2r.expect("CRITICAL - The booted kernel version is incompatible with the standard RHEL kernel.")
        assert c2r.exitstatus != 0

        # Restore the system.
        clean_up_custom_kernel(shell)
        shell("tmt-reboot -t 600")
