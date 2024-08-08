import os.path

from pathlib import Path

import pytest

from conftest import TEST_VARS


@pytest.fixture(scope="function")
def c2r_config_releasever(shell, backup_directory):
    """
    Fixture.
    Modify the releasever inside the convert2rhel configs.
    Restore back from backup after the test.
    """

    # Backup configs
    path_to_configs = "/usr/share/convert2rhel/configs/"
    assert shell(f"cp -r {path_to_configs} {backup_directory}").returncode == 0

    yield

    # Restore configs
    assert shell(f"mv -f {backup_directory}/* {path_to_configs}").returncode == 0


def test_releasever_modified_in_c2r_config(convert2rhel, os_release, c2r_config, shell, c2r_config_releasever):
    """
    Verify that releasever changes in /usr/share/convert2rhel/configs/ take precedence.
    """
    with c2r_config.replace_line(pattern="releasever=.*", repl="releasever=333"):
        with convert2rhel(
            "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
                TEST_VARS["RHSM_SERVER_URL"],
                TEST_VARS["RHSM_USERNAME"],
                TEST_VARS["RHSM_PASSWORD"],
                TEST_VARS["RHSM_POOL"],
            ),
            unregister=True,
        ) as c2r:
            c2r.expect("--releasever=333")
            c2r.sendcontrol("c")
    assert c2r.exitstatus == 1


@pytest.fixture(scope="function")
def system_release_backup(shell, backup_directory):
    """
    Fixture.
    Backup /etc/system-release before the test makes modifications to it.
    Restore the file after the test
    """
    # Backup /etc/system-release
    backup_file = os.path.join(backup_directory, "system-release.bkp")
    assert shell(f"cp /etc/system-release {backup_file}").returncode == 0

    yield

    # Restore system-release
    assert shell(f"mv -f {backup_file} /etc/system-release").returncode == 0


def test_inhibitor_releasever_noexistent_release(convert2rhel, config_at, os_release, shell, system_release_backup):
    """
    Verify that running not allowed OS release inhibits the conversion.
    Modify the /etc/system-release file to set the releasever to an unsupported version (e.g. x.1.1111)
    """
    with config_at(Path("/etc/system-release")).replace_line(
        "release .+",
        f"release {os_release.version[0]}.11.1111",
    ):
        with convert2rhel(
            "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
                TEST_VARS["RHSM_SERVER_URL"],
                TEST_VARS["RHSM_USERNAME"],
                TEST_VARS["RHSM_PASSWORD"],
                TEST_VARS["RHSM_POOL"],
            ),
            unregister=True,
        ) as c2r:
            c2r.expect(
                f"CRITICAL - {os_release.name} of version {os_release.version[0]}.11 is not allowed for conversion."
            )
        assert c2r.exitstatus == 1
