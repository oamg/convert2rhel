from pathlib import Path

import pytest

from conftest import TEST_VARS, SystemInformationRelease


@pytest.fixture(scope="function")
def backup_files(request, shell, backup_directory):
    """
    Fixture.
    Backup files or directories before the test
    and restore them after the test finishes. Need to be parametrized.
    Examples:
        @pytest.mark.parametrize("backup_files", ["/usr/share/convert2rhel/configs/"], indirect=True)
        @pytest.mark.parametrize("backup_files", ["/etc/system-release"], indirect=True)
    """
    if not hasattr(request, "param"):
        # Nothing to backup..
        print("\n 'backup_files' fixture called without parameter, doing nothing")
        return
    path_to_backup = Path(request.param)

    assert path_to_backup.exists(), f"Provided path '{path_to_backup}' to the 'backup_files' fixture does not exists"

    # Create the backup
    assert shell(f"cp -r {path_to_backup.as_posix()} {backup_directory}").returncode == 0

    yield

    # Restore configs
    shell(f"rm -rf {path_to_backup.as_posix()}")
    assert shell(f"mv -f {backup_directory}/* {path_to_backup.as_posix()}").returncode == 0


@pytest.mark.parametrize("backup_files", ["/usr/share/convert2rhel/configs/"], indirect=True)
def test_releasever_modified_in_c2r_config(backup_files, convert2rhel, shell):
    """
    Verify that releasever changes in /usr/share/convert2rhel/configs/ take precedence.
    """
    # CentOS Stream shares the config file with CentOS
    distribution = "centos" if SystemInformationRelease.is_stream else SystemInformationRelease.distribution
    config_file_name = f"{distribution}-{SystemInformationRelease.version.major}-x86_64.cfg"
    shell(f"sed -i 's/releasever=.*/releasever=420/g' /usr/share/convert2rhel/configs/{config_file_name}")
    with convert2rhel(
        "analyze -y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("--releasever=420")
        c2r.expect_exact("ERROR - (ERROR) ENSURE_KERNEL_MODULES_COMPATIBILITY::PROBLEM_WITH_PACKAGE_REPO")

    # Inhibitor expected
    assert c2r.exitstatus == 2


@pytest.mark.parametrize("backup_files", ["/etc/system-release"], indirect=True)
def test_inhibitor_releasever_noexistent_release(backup_files, convert2rhel, shell):
    """
    Verify that running not allowed OS release inhibits the conversion.
    Modify the /etc/system-release file to set the releasever to an unsupported version (e.g. x.11.1111)
    """
    # CentOS Stream release value yields only a major version mention, there is no minor version,
    # whereas other systems we test come in format major.minor
    orig_release = (
        SystemInformationRelease.version.major
        if SystemInformationRelease.is_stream
        else f"{SystemInformationRelease.version.major}.{SystemInformationRelease.version.minor}"
    )
    shell(
        f"sed -i 's/release {orig_release}/release {SystemInformationRelease.version.major}.11.11111/' /etc/system-release"
    )
    with convert2rhel(
        "analyze -y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect(
            f"CRITICAL - .* of version {SystemInformationRelease.version.major}.11 is not allowed for conversion."
        )
    assert c2r.exitstatus == 1
