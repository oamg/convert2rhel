from pathlib import Path

import pytest

from conftest import TEST_VARS


ORIGIN_KMOD_LOCATION = Path("/lib/modules/$(uname -r)/kernel/drivers/net/bonding/bonding.ko.xz")
CUSTOM_KMOD_DIRECTORY = ORIGIN_KMOD_LOCATION.parent / "custom_module_location"


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


def test_inhibitor_with_unavailable_kmod_loaded(kmod_in_different_directory, convert2rhel):
    """
    This test verifies that the check for detecting supported kernel modules in RHEL works correctly.
    If custom module is loaded the conversion has to raise:
    ENSURE_KERNEL_MODULES_COMPATIBILITY.UNSUPPORTED_KERNEL_MODULES.
    """
    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("ENSURE_KERNEL_MODULES_COMPATIBILITY::UNSUPPORTED_KERNEL_MODULES")

    assert c2r.exitstatus == 2


@pytest.mark.parametrize("environment_variables", ["CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS"], indirect=True)
def test_override_inhibitor_with_unavailable_kmod_loaded(
    kmod_in_different_directory, convert2rhel, environment_variables
):
    """
    This test verifies that setting the environment variable "CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS"
    will override the check error when there is an kernel module unavailable in RHEL detected.
    The environment variable is set through the test metadata.
    """
    with convert2rhel(
        "--serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        ),
    ) as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Detected 'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS' environment variable")
        c2r.expect("We will continue the conversion with the following kernel modules")

        c2r.sendcontrol("c")

    assert c2r.exitstatus == 1


@pytest.fixture()
def forced_kmods(shell):
    # Force load the kernel module
    assert shell("modprobe -f -v bonding").returncode == 0
    # Check for force loaded modules being flagged FE in /proc/modules
    assert "(FE)" in shell("cat /proc/modules").output

    yield

    # Clean up - unload kmod and check for force loaded modules not being in /proc/modules
    assert shell("modprobe -r -v bonding").returncode == 0
    assert "(FE)" not in shell("cat /proc/modules").output


def test_inhibitor_with_force_loaded_tainted_kmod(shell, convert2rhel, forced_kmods):
    """
    In this test case we force load kmod and verify that the convert2rhel raises:
    TAINTED_KMODS.TAINTED_KMODS_DETECTED.
    Force loaded kmods are denoted (FE) where F = module was force loaded E = unsigned module was loaded.
    Convert2RHEL sees force loaded kmod as tainted.
    """
    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        assert c2r.expect("TAINTED_KMODS::TAINTED_KMODS_DETECTED - Tainted kernel modules detected") == 0
        c2r.sendcontrol("c")

    assert c2r.exitstatus == 1


@pytest.mark.parametrize("environment_variables", ["CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP"], indirect=True)
def test_override_inhibitor_with_tainted_kmod(shell, convert2rhel, forced_kmods, environment_variables):
    """
    In this test case we force load kmod and verify that the TAINTED_KMODS.TAINTED_KMODS_DETECTED
    is overridable by setting the environment variable 'CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP'
    to '1'
    Force loaded kmods are denoted (FE) where F = module was force loaded E = unsigned module was loaded.
    Convert2RHEL sees force loaded kmod as tainted.
    """
    with convert2rhel(
        "--serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        ),
        unregister=True,
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")
        # Validate that with the envar the conversion is not inhibited with an error,
        # but just a warning is displayed and the user is allowed to proceed with a full conversion
        c2r.expect_exact("(WARNING) TAINTED_KMODS::SKIP_TAINTED_KERNEL_MODULE_CHECK")
        c2r.expect_exact("(WARNING) TAINTED_KMODS::TAINTED_KMODS_DETECTED_MESSAGE")
        # Cancel the conversion, we do not need to get further
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus == 1


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


def test_inhibitor_with_custom_built_tainted_kmod(custom_kmod, convert2rhel):
    """
    This test marks the kernel as tainted which is not supported by convert2rhel.
    We need to install specific kernel packages to build own custom kernel module.
    Verify TAINTED_KMODS.TAINTED_KMODS_DETECTED is raised.
    """

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Tainted kernel modules detected")
        c2r.expect(
            "disregard this message by setting the environment variable 'CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP'"
        )
        c2r.sendcontrol("c")

    assert c2r.exitstatus == 1
