from pathlib import Path

import pytest

from envparse import env


@pytest.fixture(scope="function")
def c2r_config_releasever(shell):
    """
    Fixture.
    Modify the releasever inside the convert2rhel configs.
    Restore back from backup after the test.
    """

    # Backup configs
    path_to_configs = "/usr/share/convert2rhel/configs/"
    backup_dir = "/tmp/c2rconfigs_backup/"
    assert shell(f"mkdir {backup_dir} && cp -r {path_to_configs} {backup_dir}").returncode == 0

    yield

    # Restore configs
    assert shell(f"mv -f {backup_dir}* {path_to_configs}").returncode == 0
    assert shell(f"rm -rf {backup_dir}").returncode == 0


@pytest.mark.test_modified_config
def test_releasever_as_mapping_config_modified(convert2rhel, os_release, c2r_config, shell, c2r_config_releasever):
    """
    Verify that releasever changes in /usr/share/convert2rhel/configs/ take precedence.
    """
    with c2r_config.replace_line(pattern="releasever=.*", repl="releasever=333"):
        with convert2rhel(
            "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
                env.str("RHSM_POOL"),
            ),
            unregister=True,
        ) as c2r:
            c2r.expect("--releasever=333")
            c2r.sendcontrol("c")
    assert c2r.exitstatus != 0


@pytest.fixture(scope="function")
def system_release_backup(shell):
    """
    Fixture.
    Backup /etc/system-release before the test makes modifications to it.
    Restore the file after the test
    """
    # Backup /etc/system-release
    backup_file = "/tmp/system-release.bkp"
    assert shell(f"cp /etc/system-release {backup_file}").returncode == 0

    yield

    # Restore system-release
    assert shell(f"mv -f {backup_file} /etc/system-release").returncode == 0


@pytest.mark.test_unknown_release
def test_releasever_as_mapping_not_existing_release(convert2rhel, config_at, os_release, shell, system_release_backup):
    """
    Verify that running not allowed OS release inhibits the conversion.
    """
    with config_at(Path("/etc/system-release")).replace_line(
        "release .+",
        f"release {os_release.version[0]}.1.1111",
    ):
        with convert2rhel(
            "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
                env.str("RHSM_POOL"),
            ),
            unregister=True,
        ) as c2r:
            c2r.expect(
                f"CRITICAL - {os_release.name} of version {os_release.version[0]}.1 is not allowed for conversion."
            )
        assert c2r.exitstatus != 0
