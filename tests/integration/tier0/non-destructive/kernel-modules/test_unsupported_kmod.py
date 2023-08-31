import os

from pathlib import Path

import pytest

from envparse import env


ORIGIN_KMOD_LOCATION = Path("/lib/modules/$(uname -r)/kernel/drivers/net/bonding/bonding.ko.xz")
CUSTOM_KMOD_DIRECTORY = ORIGIN_KMOD_LOCATION.parent / "custom_module_location"


@pytest.fixture()
def custom_kmod(shell):
    """
    Fixture to copy files needed to build custom kmod to the testing machine.
    Clean up after.
    """

    tmp_dir = "/tmp/my-test"
    files = ["my_kmod.c", "Makefile"]
    assert shell(f"mkdir {tmp_dir}").returncode == 0
    for file in files:
        assert shell(f"cp files/{file} /tmp/my-test").returncode == 0

    shell("yum -y install gcc make kernel-headers kernel-devel-$(uname -r) elfutils-libelf-devel")

    # Build own kmod form source file that has been copied to the testing machine.
    # This kmod marks the system with the P, O and E flags.
    assert shell("make -C /tmp/my-test/").returncode == 0
    assert shell("insmod /tmp/my-test/my_kmod.ko").returncode == 0

    yield

    # Clean up
    assert shell("rmmod my_kmod").returncode == 0
    assert shell("rm -rf /tmp/my-test/").returncode == 0
    shell("yum -y remove gcc make kernel-headers kernel-devel-$(uname -r) elfutils-libelf-devel")


@pytest.fixture()
def kmod_in_different_directory(shell):
    """
    This fixture moves an existing kmod to a custom location.
    Inserts kmod from custom location, thus mimics that the kmod is unsupported in RHEL.
    At the end of the test removes the loaded kernel and moves it to the original directory.
    """
    shell(f"mkdir {CUSTOM_KMOD_DIRECTORY.as_posix()}")
    shell(f"mv {ORIGIN_KMOD_LOCATION.as_posix()} {CUSTOM_KMOD_DIRECTORY.as_posix()}")
    shell("depmod")
    shell("modprobe bonding -v")

    yield

    assert shell("modprobe -r -v bonding").returncode == 0
    shell(f"mv {CUSTOM_KMOD_DIRECTORY.as_posix()}/bonding.ko.xz {ORIGIN_KMOD_LOCATION.as_posix()}")
    assert shell(f"rm -rf {CUSTOM_KMOD_DIRECTORY.as_posix()}").returncode == 0
    shell("depmod")


@pytest.mark.test_custom_module_loaded
def test_inhibit_if_custom_module_loaded(kmod_in_different_directory, convert2rhel):
    """
    This test verifies that rpmquery for detecting supported kernel modules in RHEL works correctly.
    If custom module is loaded the conversion has to be inhibited.
    """
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        ),
        unregister=True,
        expected_exitcode=1,
    ) as c2r:
        c2r.expect(
            "ENSURE_KERNEL_MODULES_COMPATIBILITY::UNSUPPORTED_KERNEL_MODULES - The following loaded kernel modules are not available in RHEL"
        )


@pytest.mark.test_custom_module_not_loaded
def test_do_not_inhibit_if_module_is_not_loaded(shell, convert2rhel):
    """
    Load the kmod from custom location.
    Verify that it is loaded.
    Remove the previously loaded 'custom' kmod and verify, the conversion is not inhibited.
    The kmod compatibility check is right before the point of no return.
    Abort the conversion right after the check.
    """
    # Move the kmod to a custom location
    shell(f"mkdir {CUSTOM_KMOD_DIRECTORY.as_posix()}")
    shell(f"mv {ORIGIN_KMOD_LOCATION.as_posix()} {CUSTOM_KMOD_DIRECTORY.as_posix()}")
    shell("depmod")
    shell("modprobe bonding -v")
    # Verify that it is loaded
    assert "bonding" in shell("cat /proc/modules").output
    # Remove the kmod and clean up
    assert shell("modprobe -r -v bonding").returncode == 0
    shell(f"mv {CUSTOM_KMOD_DIRECTORY.as_posix()}/bonding.ko.xz {ORIGIN_KMOD_LOCATION.as_posix()}")
    assert shell(f"rm -rf {CUSTOM_KMOD_DIRECTORY.as_posix()}").returncode == 0
    shell("depmod")

    # If custom module is not loaded the conversion should not be inhibited.
    with convert2rhel(
        "--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        ),
        unregister=True,
        expected_exitcode=1,
    ) as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Stop conversion before the point of no return as we do not need to run the full conversion
        assert c2r.expect("All loaded kernel modules are available in RHEL") == 0
        c2r.sendcontrol("c")


@pytest.mark.test_force_loaded_kmod
def test_inhibit_if_module_is_force_loaded(shell, convert2rhel):
    """
    In this test case we force load kmod and verify that the convert2rhel run is inhibited.
    Force loaded kmods are denoted (FE) where F = module was force loaded E = unsigned module was loaded.
    Convert2RHEL sees force loaded kmod as tainted.
    """
    # Force load the kernel module
    assert shell("modprobe -f -v bonding").returncode == 0
    # Check for force loaded modules being flagged FE in /proc/modules
    assert "(FE)" in shell("cat /proc/modules").output

    with convert2rhel("--no-rpm-va --debug", expected_exitcode=1) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        assert c2r.expect("TAINTED_KMODS::TAINTED_KMODS_DETECTED - Tainted kernel modules detected") == 0
        c2r.sendcontrol("c")

    # Clean up - unload kmod and check for force loaded modules not being in /proc/modules
    assert shell("modprobe -r -v bonding").returncode == 0
    assert "(FE)" not in shell("cat /proc/modules").output


@pytest.mark.test_tainted_kernel
def test_tainted_kernel_inhibitor(custom_kmod, convert2rhel):
    """
    This test marks the kernel as tainted which is not supported by convert2rhel.
    We need to install specific kernel packages to build own custom kernel module.
    """

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        ),
        unregister=True,
        expected_exitcode=1,
    ) as c2r:
        c2r.expect("Tainted kernel modules detected")
        c2r.sendcontrol("c")


@pytest.mark.test_unsupported_kmod_with_envar
def test_envar_overrides_unsupported_module_loaded(kmod_in_different_directory, convert2rhel):
    """
    This test verifies that setting the environment variable "CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS"
    will override the inhibition when there is RHEL unsupported kernel module detected.
    The environment variable is set through the test metadata.
    """

    with convert2rhel(
        "--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        ),
        expected_exitcode=1,
    ) as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Detected 'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS' environment variable")
        c2r.expect("We will continue the conversion with the following kernel modules")

        c2r.sendcontrol("c")

    # Remove the set environment variable
    del os.environ["CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS"]
