import filecmp
import os.path

import pytest


MODIFIED_CONTENT = """\n#This is just a placeholder test
#to verify the file won't be changed
# after the rollback"""
PACKAGES = {
    "cloud-init": "/etc/cloud/cloud.cfg",
    "NetworkManager": "/etc/NetworkManager/NetworkManager.conf",
    "yum": "/etc/logrotate.d/yum",
    "dnf": "/etc/logrotate.d/dnf",
}


@pytest.fixture
def config_files_modified(shell, backup_directory):
    """
    This fixture modifies contents of configuration files: "/etc/cloud/cloud.cfg",
    "/etc/NetworkManager/NetworkManager.conf", "/etc/logrotate.d/yum"
    and "/etc/logrotate.d/dnf" prior to running the conversion.
    After the rollback the fixture validates that the contents of the file is
    the same before and after the convert2rhel run.
    Additionally, there was a clash happening in the way convert2rhel backups files,
    if there is a file to back up that has the same name as one directory
    or another file already created, an error will be thrown to the user.
    The fixture validates this won't happen anymore.
    """
    backup_paths = {}

    modified_files_dir = os.path.join(backup_directory, "modified")
    # Create the backup directories
    if not os.path.exists(modified_files_dir):
        shell(f"mkdir -v {modified_files_dir}")

    for pkg, config in PACKAGES.items():
        file_name = os.path.basename(config)
        modified_file_path = os.path.join(modified_files_dir, f"{file_name}.modified")
        bkp_file_path = os.path.join(backup_directory, file_name)
        # Install the packages if not installed already
        if shell(f"rpm -q {pkg}").returncode == 1:
            shell(f"yum install -y {pkg}")

        # Create the config file, if not present already
        if not os.path.exists(config):
            shell(f"touch {config}")
        # Backup the original file
        shell(f"cp {config} {backup_directory}")

        # Append the modified content to the config
        # The file will be created if not already
        with open(config, "a+") as cfg:
            cfg.write(MODIFIED_CONTENT)
        # Copy the modified file for later comparison
        shell(f"cp {config} {modified_file_path}")

        backup_paths[file_name] = [modified_file_path, bkp_file_path, config]

    yield

    for file, paths in backup_paths.items():
        modified_file_path = paths[0]
        bkp_file_path = paths[1]
        default_config_path = paths[2]
        # Verify the config file got restored during rollback
        assert os.path.exists(default_config_path)

        # Verify the content is same
        assert filecmp.cmp(default_config_path, modified_file_path)

        # Restore the original file
        assert shell(f"mv -f -v {bkp_file_path} {default_config_path}").returncode == 0

    shell(f"rm -rf {modified_files_dir}")


@pytest.fixture
def config_files_removed(shell, backup_directory):
    """
    This fixture removes completely configuration files: "/etc/cloud/cloud.cfg",
    "/etc/NetworkManager/NetworkManager.conf", "/etc/logrotate.d/yum"
    and "/etc/logrotate.d/dnf" prior to running the conversion.
    After the convert2rhel performs the rollback, the fixture validates,
    that a previously absent config file is not restored at its respective
    default filepath.
    """
    backup_paths = {}

    for pkg, config in PACKAGES.items():
        file_name = os.path.basename(config)
        # Install the packages if not installed already
        if shell(f"rpm -q {pkg}").returncode == 1:
            shell(f"yum install -y {pkg}")
        # Create the config file, if not present already
        if not os.path.exists(config):
            shell(f"touch {config}")
        # Backup the original file
        shell(f"cp {config} {backup_directory}")
        bkp_file_path = os.path.join(backup_directory, file_name)
        # Remove the config to validate it won't get restored
        # during the rollback
        shell(f"rm -f {config}")

        backup_paths[file_name] = [bkp_file_path, config]

    yield

    for file, paths in backup_paths.items():
        bkp_file_path = paths[0]
        default_config_path = paths[1]
        # Verify the config did not get restored if not present
        # prior the conversion
        assert not os.path.exists(default_config_path)
        # Restore the original file
        assert shell(f"mv -f -v {bkp_file_path} {default_config_path}").returncode == 0


@pytest.mark.parametrize(
    "file_action_fixture",
    ["config_files_modified", "config_files_removed"],
)
def test_file_backup(convert2rhel, shell, file_action_fixture, request):
    """
    This test verifies correct handling of backup and restore of config files.
    "/etc/cloud/cloud.cfg", "/etc/NetworkManager/NetworkManager.conf",
    "/etc/logrotate.d/yum" and "/etc/logrotate.d/dnf" are in scope of this test.
    The following scenarios are verified:
    1/  The config files are modified with additional data
        The contents are compared pre- and post-conversion analysis task
        and should remain the same.
    2/  The config files are removed pre-conversion analysis task
        and should remain absent post-rollback.
    Additionally, validates that a file clash does not happen during a backup.
    There was a clash happening in the way convert2rhel backups files,
    if there is a file to back up that has the same name as one directory
    or another file already created, an error will be thrown to the user.
    For that scenario we utilize "/etc/logrotate.d/yum"
    and "/etc/logrotate.d/dnf" files.
    """
    request.getfixturevalue(file_action_fixture)
    with convert2rhel("analyze -y --debug") as c2r:
        # Verify the rollback starts and analysis report is printed out
        c2r.expect("Abnormal exit! Performing rollback")
        c2r.expect("Pre-conversion analysis report")
    assert c2r.exitstatus == 2
