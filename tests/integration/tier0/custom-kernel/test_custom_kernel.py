import os

import pytest


SYSTEM_RELEASE = os.environ.get("SYSTEM_RELEASE")

DISTRO_KERNEL_MAPPING = {
    "centos-7": {
        "original_kernel": "kernel-3.10.0-1160.76.1.el7.x86_64",
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL7/latest/x86_64/getPackage/kernel-3.10.0-1160.76.1.0.1.el7.x86_64.rpm",
    },
    "centos-8.4": {
        "original_kernel": "kernel-core-4.18.0-305.25.1.el8_4.x86_64",
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/4/baseos/base/x86_64/getPackage/kernel-core-4.18.0-305.el8.x86_64.rpm",
    },
    "centos-8.5": {
        "original_kernel": "kernel-core-4.18.0-348.7.1.el8_5.x86_64",
        "custom_kernel": "https://yum.oracle.com/repo/OracleLinux/OL8/5/baseos/base/x86_64/getPackage/kernel-core-4.18.0-348.el8.x86_64.rpm",
    },
    "oracle-7": {
        "original_kernel": "kernel-uek-5.4.17-2136.307.3.1.el7uek.x86_64",
        "custom_kernel": "http://mirror.centos.org/centos/7/os/x86_64/Packages/kernel-3.10.0-1160.el7.x86_64.rpm",
    },
    "oracle-8.4": {
        "original_kernel": "kernel-uek-5.4.17-2102.204.4.4.el8uek.x86_64",
        "custom_kernel": " https://vault.centos.org/centos/8.4.2105/BaseOS/x86_64/os/Packages/kernel-core-4.18.0-305.25.1.el8_4.x86_64.rpm",
    },
    # Install CentOS 8.5 kernel
    "oracle-8.6": {
        "original_kernel": "kernel-uek-5.4.17-2136.307.3.1.el8uek.x86_64",
        "custom_kernel": "https://vault.centos.org/centos/8.5.2111/BaseOS/x86_64/os/Packages/kernel-core-4.18.0-348.7.1.el8_5.x86_64.rpm",
    },
}


def install_custom_kernel(shell):
    """
    Install CentOS kernel on Oracle Linux and vice versa to mimic the custom
    kernel that is not signed by the running OS official vendor.
    """
    original_kernel, custom_kernel = DISTRO_KERNEL_MAPPING[SYSTEM_RELEASE].values()
    kernel_release = custom_kernel.rsplit("/")[-1].replace(".rpm", "").split("-", 2)[-1]
    if "centos-8.5" in SYSTEM_RELEASE:
        # We have to remove this kernel-core package first, as the ones we try
        # to install from Oracle Linux are the same version.
        assert shell("yum remove %s -y" % original_kernel) == 0

    assert shell("yum install %s -y" % custom_kernel).returncode == 0
    assert (
        shell(
            "grubby --set-default=/boot/vmlinuz-%s" % kernel_release,
        ).returncode
        == 0
    )

    shell("tmt-reboot -t 600")


def clean_up_custom_kernel(shell):
    """
    Remove the current installed kernel and install the machine default kernel.
    """
    original_kernel, custom_kernel = DISTRO_KERNEL_MAPPING[SYSTEM_RELEASE].values()
    original_kernel_release = original_kernel.rsplit("/")[-1].replace(".rpm", "").split("-", 2)[-1]
    custom_kernel_release = custom_kernel.rsplit("/")[-1].replace(".rpm", "")
    assert shell("rpm -e %s" % custom_kernel_release).returncode == 0

    # Install back the CentOS 8.5 original kernel
    if "centos-8.5" in SYSTEM_RELEASE:
        assert shell("yum install %s -y" % original_kernel).returncode == 0

    assert (
        shell(
            "grubby --set-default /boot/vmlinuz-%s" % original_kernel_release,
        ).returncode
        == 0
    )


def get_default_kernel(shell):
    """Get the default kernel package name."""
    vmlinuz_path = shell("grubby --default-kernel").output

    kernel_pkg = shell("rpm -qf %s" % vmlinuz_path)

    return kernel_pkg


@pytest.mark.custom_kernel
def test_custom_kernel(convert2rhel, shell):
    """
    Run the conversion with custom kernel installed on the system.
    """
    os_vendor = "CentOS"
    if "oracle" in SYSTEM_RELEASE:
        os_vendor = "Oracle"

    if os.environ["TMT_REBOOT_COUNT"] == "0":
        install_custom_kernel(shell)
    elif os.environ["TMT_REBOOT_COUNT"] == "1":
        with convert2rhel("--no-rpm-va --debug") as c2r:
            c2r.expect("WARNING - Custom kernel detected. The booted kernel needs to be signed by {}".format(os_vendor))
            c2r.expect("CRITICAL - The booted kernel version is incompatible with the standard RHEL kernel.")
        assert c2r.exitstatus != 0

        # Restore the system.
        clean_up_custom_kernel(shell)
        shell("tmt-reboot -t 600")
