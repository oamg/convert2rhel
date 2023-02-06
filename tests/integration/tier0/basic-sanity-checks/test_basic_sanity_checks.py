import os
import re
import subprocess

import pytest


CONVERT2RHEL_FACTS_FILE = "/etc/rhsm/facts/convert2rhel.facts"


@pytest.mark.root_privileges
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


@pytest.mark.manpage
def test_manpage_exists(shell):
    """
    Check if manpage exists.
    """
    assert shell("man -w convert2rhel").returncode == 0


@pytest.mark.smoke
def test_smoke_basic(shell):
    """
    Check basic behaviour.
    Show help and exit.
    Exit on first prompt passing 'no'.
    """
    assert shell("convert2rhel --help").returncode == 0
    assert shell("convert2rhel -h").returncode == 0
    assert shell("convert2rhel --no-rpm-va <<< n").returncode != 0


@pytest.mark.log_file_exists
def test_log_file_verification(shell):
    """
    Verify that the log file was created by the convert2rhel run.
    """
    assert shell("convert2rhel --no-rpm-va <<< n").returncode != 0

    assert os.path.exists("/var/log/convert2rhel/convert2rhel.log")


@pytest.fixture(scope="function")
def c2r_version(request):
    """
    A fixture that updates the version value in a file.
    """
    # Find where the site packages for Convert2RHEL are and backup the original version.
    path_to_version = subprocess.check_output(
        ["find", "/usr/lib/", "-path", "*/convert2rhel/__init__.py", "-printf", "%p"]
    ).decode("utf-8")
    # Load the original value to restore later
    with open(path_to_version, "r") as version_file:
        old_version_content = version_file.read()

    def _update_c2r_version(version):
        """
        Modify the Convert2RHEL version value in the __init__.py file.
        We want to simulate the running version is older/newer than in the repositories.
        """
        with open(path_to_version, "w") as version_file:
            # Update the version
            version_pattern = r'__version__ = "(\d+\.\d+\.\d+)"'
            updated_version_content = re.sub(version_pattern, '__version__ = "{}"'.format(version), old_version_content)
            version_file.write(updated_version_content)

    yield _update_c2r_version

    def _restore_c2r_version():
        # Update the value back to the original
        with open(path_to_version, "w") as version_file:
            version_file.write(old_version_content)

    _restore_c2r_version()


@pytest.mark.version_latest_or_newer
@pytest.mark.parametrize("version", ["42.0.0"])
def test_c2r_latest_newer(convert2rhel, c2r_version, version):
    """
    Verify, that running latest or newer version does not interfere with running the conversion.
    """
    c2r_version(version)
    with convert2rhel("--no-rpm-va --debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        assert c2r.expect("Latest available Convert2RHEL version is installed.", timeout=300) == 0

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")


@pytest.mark.version_older_no_envar
@pytest.mark.parametrize("version", ["0.01.0"])
def test_c2r_latest_older_inhibit(convert2rhel, c2r_version, version):
    """
    Check if running older version inhibits the conversion.
    """

    c2r_version(version)

    with convert2rhel("--no-rpm-va --debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        assert c2r.expect("CRITICAL - You are currently running 0.01", timeout=300) == 0
        assert c2r.expect("Only the latest version is supported for conversion.", timeout=300) == 0
    assert c2r.exitstatus != 0


@pytest.fixture
def older_version_envar():
    # Set the environment variable
    os.environ["CONVERT2RHEL_ALLOW_OLDER_VERSION"] = "1"

    yield
    # Delete the environment variable
    del os.environ["CONVERT2RHEL_ALLOW_OLDER_VERSION"]


@pytest.mark.version_older_with_envar
@pytest.mark.parametrize("version", ["0.01.0"])
def test_c2r_latest_older_unsupported_version(convert2rhel, c2r_version, version, older_version_envar):
    """
    Verify, that running older version of Convert2RHEL with the environment
    variable "CONVERT2RHEL_ALLOW_OLDER_VERSION" continues the conversion.
    Running older version of convert2rhel on OS major version 6 or older should inhibit either way.
    """
    c2r_version(version)

    with convert2rhel("--no-rpm-va --debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        assert c2r.expect("You are currently running 0.01", timeout=300) == 0
        assert (
            c2r.expect(
                "'CONVERT2RHEL_ALLOW_OLDER_VERSION' environment variable detected, continuing conversion",
                timeout=300,
            )
            == 0
        )
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
    assert c2r.exitstatus != 0


@pytest.mark.clean_cache
def test_clean_cache(convert2rhel):
    """
    Verify that the yum clean is done before any other check that c2r does
    """
    with convert2rhel("--no-rpm-va --debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        assert c2r.expect("Prepare: Clean yum cache metadata", timeout=300) == 0
        assert c2r.expect("Cached repositories metadata cleaned successfully.", timeout=300) == 0

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")


@pytest.mark.log_rhsm_error
def test_rhsm_error_logged(convert2rhel):
    """
    Test if the OSError for RHSM certificate being removed
    is not being logged in cases the certificate is not installed yet.
    """
    with convert2rhel("--debug --no-rpm-va") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
        assert c2r.expect("No RHSM certificates found to be removed.", timeout=300) == 0

    # Verify the error message is not present in the log file
    with open("/var/log/convert2rhel/convert2rhel.log", "r") as logfile:
        for line in logfile:
            assert "ERROR - OSError(2): No such file or directory" not in line


@pytest.mark.variant_message
def test_check_variant_message(convert2rhel):
    """
    Run Convert2RHEL with deprecated -v/--variant option and verify that the warning message is shown.
    """
    # Run c2r with --variant option
    with convert2rhel("--no-rpm-va --debug --variant Server") as c2r:
        c2r.expect("WARNING - The -v|--variant option is not supported anymore and has no effect")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
    assert c2r.exitstatus != 0

    # Run c2r with --variant option empty
    with convert2rhel("--no-rpm-va --debug --variant") as c2r:
        c2r.expect("WARNING - The -v|--variant option is not supported anymore and has no effect")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
    assert c2r.exitstatus != 0

    # Run c2r with -v option
    with convert2rhel("--no-rpm-va --debug -v Client") as c2r:
        c2r.expect("WARNING - The -v|--variant option is not supported anymore and has no effect")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
    assert c2r.exitstatus != 0

    # Run c2r with -v option empty
    with convert2rhel("--no-rpm-va --debug -v") as c2r:
        c2r.expect("WARNING - The -v|--variant option is not supported anymore and has no effect")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
    assert c2r.exitstatus != 0


@pytest.mark.data_collection_acknowledgement
def test_data_collection_acknowledgement(shell, convert2rhel):
    """
    This test verifies, that information about data collection is printed out
    and user is asked for acknowledgement to continue.
    Verify, that without acknowledgement the convert2rhel.facts file is not created.
    """
    # Remove facts from previous runs.
    shell(f"rm -f {CONVERT2RHEL_FACTS_FILE}")
    # Remove envar disabling telemetry just in case.
    if os.getenv("CONVERT2RHEL_DISABLE_TELEMETRY"):
        del os.environ["CONVERT2RHEL_DISABLE_TELEMETRY"]

    with convert2rhel("--no-rpm-va --debug") as c2r:
        assert c2r.expect("Prepare: Inform about telemetry", timeout=300) == 0
        assert (
            c2r.expect("The convert2rhel utility uploads the following data about the system conversion", timeout=300)
            == 0
        )
        c2r.expect("Continue with the system conversion", timeout=300)
        c2r.sendline("n")

        # Verify the file is not created if user refuses the collection.
        assert not os.path.exists(CONVERT2RHEL_FACTS_FILE)

    assert c2r.exitstatus != 0


@pytest.mark.disable_data_collection
def test_disable_data_collection(shell, convert2rhel):
    """
    This test verifies functionality of CONVERT2RHEL_DISABLE_TELEMETRY envar.
    The data collection should be disabled, therefore convert2rhel.facts file should not get created.
    """
    # Remove facts from previous runs.
    shell(f"rm -f {CONVERT2RHEL_FACTS_FILE}")
    # Set envar to disable data collection
    os.environ["CONVERT2RHEL_DISABLE_TELEMETRY"] = "1"

    with convert2rhel("--no-rpm-va --debug") as c2r:
        assert c2r.expect("Prepare: Inform about telemetry", timeout=300) == 0
        assert c2r.expect("Skipping, telemetry disabled.", timeout=300) == 0

        c2r.expect("Continue with the system conversion", timeout=300)
        c2r.sendline("n")

        # Verify the file is not created if CONVERT2RHEL_DISABLE_TELEMETRY is set.
        assert not os.path.exists(CONVERT2RHEL_FACTS_FILE)

    assert c2r.exitstatus != 0

    # Remove envar disabling telemetry.
    del os.environ["CONVERT2RHEL_DISABLE_TELEMETRY"]
