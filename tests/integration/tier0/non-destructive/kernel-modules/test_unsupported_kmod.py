from pathlib import Path

import pytest

from conftest import TEST_VARS


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
def test_error_if_custom_module_loaded(kmod_in_different_directory, convert2rhel):
    """
    This test verifies that rpmquery for detecting supported kernel modules in RHEL works correctly.
    If custom module is loaded the conversion has to raise:
    ENSURE_KERNEL_MODULES_COMPATIBILITY.UNSUPPORTED_KERNEL_MODULES.
    """
    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("ENSURE_KERNEL_MODULES_COMPATIBILITY::UNSUPPORTED_KERNEL_MODULES")

    assert c2r.exitstatus != 0


@pytest.mark.test_custom_module_not_loaded
def test_do_not_error_if_module_is_not_loaded(shell, convert2rhel):
    """
    Load the kmod from custom location.
    Verify that it is loaded.
    Remove the previously loaded 'custom' kmod and verify, the conversion
    does not raise the ENSURE_KERNEL_MODULES_COMPATIBILITY.UNSUPPORTED_KERNEL_MODULES.
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

    # If custom module is not loaded the conversion should not raise an error
    with convert2rhel(
        "--serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Stop conversion before the point of no return as we do not need to run the full conversion
        assert c2r.expect("All loaded kernel modules are available in RHEL") == 0
        c2r.sendcontrol("c")

    assert c2r.exitstatus != 0


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


@pytest.mark.test_force_loaded_kmod
def test_error_if_module_is_force_loaded(shell, convert2rhel, forced_kmods):
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

        assert c2r.expect("TAINTED_KMODS::TAINTED_KMODS_DETECTED - Tainted kernel modules detected") == 0
        c2r.sendcontrol("c")

    assert c2r.exitstatus != 0


@pytest.mark.parametrize("envars", [["CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP"]])
@pytest.mark.test_tainted_kernel_modules_check_override
def test_tainted_kernel_modules_check_override(shell, convert2rhel, forced_kmods, environment_variables, envars):
    """
    In this test case we force load kmod and verify that the TAINTED_KMODS.TAINTED_KMODS_DETECTED
    is overridable by setting the environment variable 'CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP'
    to '1'
    Force loaded kmods are denoted (FE) where F = module was force loaded E = unsigned module was loaded.
    Convert2RHEL sees force loaded kmod as tainted.
    """
    environment_variables(envars)
    with convert2rhel(
        "--serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
        ),
        unregister=True,
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")
        # Validate that with the envar the conversion is not inhibited with an error,
        # but just a warning is displayed and the user is allowed to proceed with a full conversion
        c2r.expect_exact("(WARNING) TAINTED_KMODS::SKIP_TAINTED_KERNEL_MODULE_CHECK")
        c2r.expect_exact("(WARNING) TAINTED_KMODS::TAINTED_KMODS_DETECTED_MESSAGE")
        # Cancel the conversion, we do not need to get further
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus != 0


@pytest.mark.test_tainted_kernel_modules_error
def test_tainted_kernel_modules_error(custom_kmod, convert2rhel):
    """
    This test marks the kernel as tainted which is not supported by convert2rhel.
    We need to install specific kernel packages to build own custom kernel module.
    Verify TAINTED_KMODS.TAINTED_KMODS_DETECTED is raised.
    """

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Tainted kernel modules detected")
        c2r.expect(
            "disregard this message by setting the environment variable 'CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP'"
        )
        c2r.sendcontrol("c")

    assert c2r.exitstatus != 0


@pytest.mark.parametrize("envars", [["CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS"]])
@pytest.mark.test_unsupported_kmod_with_envar
def test_envar_overrides_unsupported_module_loaded(
    kmod_in_different_directory, convert2rhel, environment_variables, envars
):
    """
    This test verifies that setting the environment variable "CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS"
    will override the check error when there is RHEL unsupported kernel module detected.
    The environment variable is set through the test metadata.
    """
    environment_variables(envars)
    with convert2rhel(
        "--serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Detected 'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS' environment variable")
        c2r.expect("We will continue the conversion with the following kernel modules")

        c2r.sendcontrol("c")

    assert c2r.exitstatus != 0
