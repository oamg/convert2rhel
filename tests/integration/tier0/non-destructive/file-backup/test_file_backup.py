import os.path

import pytest


@pytest.fixture
def config_files(shell):
    """
    This fixture either modifies contents or removes completely two
    configuration files (cloud-init, NetworkManager).
    The action is based on test-related custom envar.
    """

    modified_content = """\n#This is just a placeholder test
    #to verify the file won't be changed
    # after the rollback"""
    packages = {"cloud-init": "/etc/cloud/cloud.cfg", "NetworkManager": "/etc/NetworkManager/NetworkManager.conf"}
    backup_dir = "/tmp/c2r_tests_backup/"

    shell(f"mkdir {backup_dir}")

    for pkg, config in packages.items():
        # Backup the original file
        shell(f"cp {config} {backup_dir}")
        # Install the packages if not installed already
        if "is not installed" in shell(f"rpm -q {pkg}").output:
            shell(f"yum install -y {pkg}")
        # If we check for file modification being in place after the rollback
        if os.environ.get("C2R_TESTS_MODIFIED_CONFIGS"):
            # Append the modified content to the config
            # The file will be created if not already
            with open(config, "a+") as cfg:
                cfg.write(modified_content)
                cfg.seek(0)
                modified_file_data = cfg.read()
        else:
            # Remove the config to validate it won't get restored
            # during the rollback
            shell(f"rm -f {config}")

    yield

    for pkg, config in packages.items():
        # Verify the packages are still installed
        assert shell(f"rpm -q {pkg}").returncode == 0
        # Verify the pre-conversion and post-conversion
        if os.environ.get("C2R_TESTS_MODIFIED_CONFIGS"):
            # Verify the config file got restored during rollback
            assert os.path.exists(config)
            # Read the restored content
            with open(config, "r") as cfg:
                restored_file_data = cfg.read()

            # Verify the content is same
            assert modified_file_data == restored_file_data
        else:
            # Verify the config did not get restored if not present
            # prior the conversion
            assert not os.path.exists(config)

        # Restore the original file
        shell(f"mv -f {backup_dir}{config.rsplit('/', maxsplit=1)[-1]} {config}")


@pytest.fixture
def mod_config_envar():
    """
    Fixture to set test related envar.
    """
    os.environ["C2R_TESTS_MODIFIED_CONFIGS"] = "1"

    yield

    del os.environ["C2R_TESTS_MODIFIED_CONFIGS"]


@pytest.mark.parametrize("envar", [None, mod_config_envar])
@pytest.mark.test_file_backup
def test_file_backup(convert2rhel, shell, envar, config_files):
    """
    This test verifies correct handling backup and restore of config files.
    Two configs (cloud-init, NetworkManager) are in scope of this test.
    The following scenarios are verified:
    1/  The config files are modified with additional data
        The contents are compared pre- and post-conversion analysis task
        and should remain the same.
    2/  The config files are removed pre-conversion analysis task
        and should remain absent post-rollback.
    """
    with convert2rhel("analyze -y --debug") as c2r:
        # Verify the rollback starts and analysis report is printed out
        c2r.expect("Abnormal exit! Performing rollback")
        c2r.expect("Pre-conversion analysis report")
