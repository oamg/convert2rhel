from pathlib import Path

import pytest

from envparse import env


ORIGIN_KMOD_LOCATION = Path("/lib/modules/$(uname -r)/kernel/drivers/net/bonding/bonding.ko.xz")
CUSTOM_KMOD_DIRECTORY = ORIGIN_KMOD_LOCATION.parent / "custom_module_location"


def prepare_custom_kmod(shell):
    """
    Helper function.
    Copy files needed to build custom kmod to the testing machine.
    """

    tmp_dir = "/tmp/my-test"
    files = ["my_kmod.c", "Makefile"]
    assert shell(f"mkdir {tmp_dir}").returncode == 0
    for file in files:
        assert shell(f"cp files/{file} /tmp/my-test").returncode == 0


def insert_custom_kmod(shell):
    """
    Helper function.
    Move an existing kmod to a custom location.
    Insert kmod from custom location, thus mimic that the kmod is unsupported in RHEL.
    """
    shell(f"mkdir {CUSTOM_KMOD_DIRECTORY.as_posix()}")
    shell(f"mv {ORIGIN_KMOD_LOCATION.as_posix()} {CUSTOM_KMOD_DIRECTORY.as_posix()}")
    shell("depmod")
    shell("modprobe bonding -v")


def restore_custom_kmod(shell):
    """
    Helper function.
    Move previously loaded kmod to an original directory.
    """
    assert shell("modprobe -r -v bonding").returncode == 0
    shell(f"mv {CUSTOM_KMOD_DIRECTORY.as_posix()}/bonding.ko.xz {ORIGIN_KMOD_LOCATION.as_posix()}")
    assert shell(f"rm -rf {CUSTOM_KMOD_DIRECTORY.as_posix()}").returncode == 0
    shell("depmod")


@pytest.mark.custom_module_loaded
def test_inhibit_if_custom_module_loaded(shell, convert2rhel):
    """
    This test verifies that rpmquery for detecting supported kernel modules in RHEL works correctly.
    If custom module is loaded the conversion has to be inhibited.
    """
    insert_custom_kmod(shell)
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("CRITICAL - The following loaded kernel modules are not available in RHEL")
    assert c2r.exitstatus != 0

    # Restore the machine
    restore_custom_kmod(shell)


@pytest.mark.custom_module_not_loaded
def test_do_not_inhibit_if_module_is_not_loaded(shell, convert2rhel, get_system_release):
    """
    Load the kmod from custom location.
    Verify that it is loaded.
    Remove the previously loaded 'custom' kmod and verify, the conversion is not inhibited.
    The kmod compatibility check is right before the point of no return.
    Abort the conversion right after the check.
    """
    insert_custom_kmod(shell)
    assert "bonding" in shell("cat /proc/modules").output
    restore_custom_kmod(shell)

    if "oracle-7" in get_system_release:
        prompt_amount = 3
    elif "oracle-8" in get_system_release:
        prompt_amount = 2
    elif "centos" in get_system_release:
        prompt_amount = 4
    # If custom module is not loaded the conversion should not be inhibited.
    with convert2rhel(
        "--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        ),
        unregister=True,
    ) as c2r:
        while prompt_amount > 0:
            c2r.expect("Continue with the system conversion?")
            c2r.sendline("y")
            prompt_amount -= 1

        # Stop conversion before the point of no return as we do not need to run the full conversion
        assert c2r.expect("All loaded kernel modules are available in RHEL", timeout=600) == 0
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
        assert c2r.exitstatus != 0


@pytest.mark.force_loaded_kmod
def test_inhibit_if_module_is_force_loaded(shell, convert2rhel, get_system_release):
    """
    Test force loads kmod and verifies that Convert2RHEL run is being inhibited.
    Force loaded kmods are denoted (FE) where F = module was force loaded E = unsigned module was loaded.
    Convert2RHEL sees force loaded kmod as tainted.
    """
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


@pytest.mark.tainted_kernel
def test_tainted_kernel_inhibitor(shell, convert2rhel):
    """
    This test marks the kernel as tainted which is not supported by Convert2RHEL.
    We need to install specific kernel packages to build own custom kernel module.
    """
    # Copy files needed to build custom kmod to the testing machine
    prepare_custom_kmod(shell)

    shell("yum -y install gcc make kernel-headers kernel-devel-$(uname -r) elfutils-libelf-devel")

    # Build own kmod form source file that has been copied to the testing machine.
    # This kmod marks the system with the P, O and E flags.
    assert shell("make -C /tmp/my-test/").returncode == 0
    assert shell("insmod /tmp/my-test/my_kmod.ko").returncode == 0

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Tainted kernel modules detected")
    assert c2r.exitstatus != 0
    # Clean up
    assert shell("rmmod my_kmod").returncode == 0
    assert shell("rm -rf /tmp/my-test/").returncode == 0
