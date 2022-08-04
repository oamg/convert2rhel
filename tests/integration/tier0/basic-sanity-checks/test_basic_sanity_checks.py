import os
import platform
import subprocess


booted_os = platform.platform()


def test_check_user_privileges(shell):
    """
    Check if the Convert2RHEL is only being possible to run as a root user.
    """
    user = "testuser"
    # Create non-root user if not created already
    assert shell(f"useradd '{user}'").returncode == 0
    # Set user to non-root entity 'testuser' and run c2r
    result = shell("runuser -l testuser -c 'convert2rhel'")
    # Check the program exits as it is required to be run by root
    assert result.returncode != 0
    # Check the program exits for the correct reason
    assert (
        result.output == "The tool needs to be run under the root user.\n" "\n" "No changes were made to the system.\n"
    )
    # Delete testuser (if present)
    assert shell(f"userdel -r '{user}'").returncode == 0


def test_manpage_exists(shell):
    """
    Check if manpage exists.
    """
    assert shell("man -w convert2rhel").returncode == 0


def test_smoke_basic(shell):
    """
    Check basic behaviour.
    Show help and exit.
    Exit on first prompt passing 'no'.
    """
    assert shell("convert2rhel --help").returncode == 0
    assert shell("convert2rhel -h").returncode == 0
    assert shell("convert2rhel <<< n").returncode != 0


# Find where the site packages for Convert2RHEL are and backup the original version.
PATH_TO_VERSION = subprocess.check_output(
    ["find", "/usr/lib/", "-path", "*/convert2rhel/__init__.py", "-printf", "%p"]
).decode("utf-8")
os.system(f"cp {PATH_TO_VERSION} /tmp/")


def change_c2r_version(version):
    """
    Modify the __init__.py in which the version is stored.
    """
    with open(PATH_TO_VERSION, "r+") as version_file:
        version_file.write(f"__version__ = '{version}'")


def test_c2r_latest_newer(convert2rhel):
    """
    Check if running latest or newer version continues the conversion.
    """
    change_c2r_version(42.0)

    with convert2rhel(f"--no-rpm-va --debug") as c2r:
        assert c2r.expect("Latest available convert2rhel version is installed.") == 0
        assert c2r.expect("Continuing conversion.") == 0
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    # Clean up
    os.system(f"cp /tmp/__init__.py {PATH_TO_VERSION}")


def test_c2r_latest_older_inhibit(convert2rhel):
    """
    Check if running older version inhibits the conversion.
    """
    change_c2r_version(0.01)

    with convert2rhel(f"--no-rpm-va --debug") as c2r:
        assert c2r.expect("CRITICAL - You are currently running 0.01 ") == 0
        assert c2r.expect("Only the latest version is supported for conversion.") == 0
    assert c2r.exitstatus != 0

    # Clean up
    os.system(f"cp /tmp/__init__.py {PATH_TO_VERSION}")


def test_c2r_latest_older_unsupported_version(convert2rhel):
    """
    Check if running older version with the environment
    variable "CONVERT2RHEL_UNSUPPORTED_VERSION" continues the conversion.
    Running older version of Convert2RHEL on epel major version 6 or older should inhibit either way.
    """
    change_c2r_version(0.01)

    os.environ["CONVERT2RHEL_UNSUPPORTED_VERSION"] = "1"

    with convert2rhel(f"--no-rpm-va --debug") as c2r:
        if "centos-6" in booted_os or "oracle-6" in booted_os:
            assert c2r.expect("You are currently running 0.01") == 0
            assert c2r.expect("Only the latest version is supported for conversion.") == 0

        else:
            assert c2r.expect("You are currently running 0.01") == 0
            assert c2r.expect("'CONVERT2RHEL_UNSUPPORTED_VERSION' environment detected, continuing conversion") == 0
            c2r.expect("Continue with the system conversion?")
            c2r.sendline("n")
    assert c2r.exitstatus != 0

    # Clean up
    os.system(f"cp /tmp/__init__.py {PATH_TO_VERSION}")
    del os.environ["CONVERT2RHEL_UNSUPPORTED_VERSION"]


def test_clean_cache(convert2rhel):
    # Test that the yum clean is done before any other check that c2r does
    with convert2rhel("--no-rpm-va --debug") as c2r:
        assert c2r.expect("Prepare: Clean yum cache metadata") == 0
        assert c2r.expect("Cached yum metadata cleaned successfully.") == 0

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")


def test_rhsm_error_logged(convert2rhel):
    """
    Test if the OSError for RHSM certificate being removed
    is not being logged in cases the certificate is not installed yet.
    """
    with convert2rhel("--debug --no-rpm-va") as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
        assert c2r.expect("DEBUG - No RHSM certificates found to be removed") == 0

    # Check for error not present in log file
    with open("/var/log/convert2rhel/convert2rhel.log", "r") as logfile:
        for line in logfile:
            assert "ERROR - OSError(2): No such file or directory" not in line
