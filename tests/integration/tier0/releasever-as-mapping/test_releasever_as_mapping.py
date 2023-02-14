from pathlib import Path

from envparse import env


def test_releasever_as_mapping_config_modified(convert2rhel, os_release, c2r_config):
    """Test if config changes takes precedence."""
    with c2r_config.replace_line(pattern="releasever=.*", repl=f"releasever=333"):
        with convert2rhel(
            "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
                env.str("RHSM_POOL"),
            )
        ) as c2r:
            c2r.expect("--releasever=333")
            c2r.send(chr(3))
    assert c2r.exitstatus == 1


def test_releasever_as_mapping_not_existing_release(convert2rhel, config_at, os_release):
    """Test unknown release."""
    with config_at(Path("/etc/system-release")).replace_line(
        "release .+",
        f"release {os_release.version[0]}.1.1111",
    ):
        with convert2rhel(
            "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
                env.str("RHSM_POOL"),
            )
        ) as c2r:
            c2r.expect(
                f"CRITICAL - {os_release.name} of version {os_release.version[0]}.1 is not allowed for conversion."
            )
        assert c2r.exitstatus == 1
