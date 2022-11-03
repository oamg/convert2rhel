import platform

from pathlib import Path

import pytest

from envparse import env


system_version = platform.platform()


@pytest.fixture()
def insert_custom_kmod(shell):
    """
    Move the kernel module to custom location, so it is marked as custom.
    Then load the kernel module.
    """

    def factory():
        origin_kmod_loc = Path("/lib/modules/$(uname -r)/kernel/drivers/net/bonding/bonding.ko.xz")
        new_kmod_dir = origin_kmod_loc.parent / "custom_module_location"

        shell(f"mkdir {new_kmod_dir.as_posix()}")
        shell(f"mv {origin_kmod_loc.as_posix()} {new_kmod_dir.as_posix()}")
        shell("depmod")
        shell(f"modprobe bonding -v")

    return factory


def test_inhibit_if_custom_module_loaded(insert_custom_kmod, convert2rhel):
    """
    This test verifies that rpmquery for detecting supported kernel modules in RHEL works correctly.
    If custom module is loaded the conversion has to be inhibited.
    """
    insert_custom_kmod()
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("The following loaded kernel modules are not available in RHEL")
    assert c2r.exitstatus != 0


def test_do_not_inhibit_if_module_is_not_loaded(shell, convert2rhel):
    """
    Test removes previously loaded custom module and runs the conversion.
    The kmod compatibility checks is right before the point of no return.
    Abort the conversion right after the check.
    """
    assert shell("modprobe -r -v bonding").returncode == 0

    if "oracle-7" in system_version or "centos-7" in system_version:
        prompt_amount = 3
    elif "oracle-8" in system_version:
        prompt_amount = 2
    elif "centos-8" in system_version:
        prompt_amount = 3
    # If custom module is not loaded the conversion is not inhibited.
    with convert2rhel(
        "--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        while prompt_amount > 0:
            c2r.expect("Continue with the system conversion?")
            c2r.sendline("y")
            prompt_amount -= 1

        # Stop conversion before the point of no return as we do not need to run the full conversion
        # with the check for kompatible kernel modules being right before the PONR.
        assert c2r.expect("All loaded kernel modules are available in RHEL.", timeout=600) == 0
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
        assert c2r.exitstatus != 0


def test_do_not_inhibit_if_module_is_force_loaded(shell, convert2rhel):
    """
    Test force loads kmod and verifies that Convert2RHEL run is being inhibited.
    Force loaded kmods are denoted (FE) where F = module was force loaded E = unsigned module was loaded.
    Convert2RHEL sees force loaded kmod as tainted.
    """
    if "oracle-7" not in system_version and "centos-7" not in system_version:
        # Force load the kernel module
        assert shell("modprobe -f -v bonding").returncode == 0
        # Check for force loaded modules being flagged FE in /proc/modules
        assert "(FE)" in shell("cat /proc/modules").output

        with convert2rhel("--no-rpm-va --debug") as c2r:
            assert c2r.expect("Tainted kernel modules detected") == 0
            assert c2r.exitstatus != 0

        # Clean up - unload kmod and check for force loaded modules not being in /proc/modules
        assert shell("modprobe -r -v bonding").returncode == 0
        assert "(FE)" not in shell("cat /proc/modules").output


def test_tainted_kernel_inhibitor(shell, convert2rhel):
    """
    This test marks the kernel as tainted which is not supported by Convert2RHEL.
    We need to install specific kernel packages to build own custom kernel module.
    Build own kmod from source file that has been copied to the testing machine during preparation phase.
    This kmod marks the system with the P, O and E flags.
    """

    # Install kernel packages
    shell("yum -y install gcc make kernel-headers kernel-devel-$(uname -r) elfutils-libelf-devel")

    # Build own kmod form source file that has been copied to the testing machine during preparation phase.
    # This kmod marks the system with the P, O and E flags.
    assert shell("make -C /tmp/my-test/").returncode == 0
    assert shell("insmod /tmp/my-test/my_kmod.ko").returncode == 0

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Tainted kernel modules detected")
    assert c2r.exitstatus != 0
