import sys

import pexpect

from envparse import env


def test_remove_excluded_pkgs(shell):
    """Ensure c2r removes pkgs, which specified as excluded_pkgs in config."""

    excluded_pkg_1 = "centos-gpg-keys"
    excluded_pkg_2 = "centos-backgrounds"

    # install some of excluded packages
    assert (
        shell(
            f"yum install -y {excluded_pkg_1} {excluded_pkg_2}",
        ).returncode
        == 0
    )

    # run utility until the reboot
    c2r = pexpect.spawn(
        (
            "convert2rhel -y --no-rpm-va "
            "--serverurl {} --username {} "
            "--password {} --pool {} "
            "--debug "
            "--no-rpm-va"
        ).format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        ),
        encoding="utf-8",
        timeout=30 * 60,
    )
    c2r.logfile_read = sys.stdout
    c2r.expect(pexpect.EOF)
    c2r.close()
    assert c2r.exitstatus == 0
    shell("subscription-manager unregister")

    # check excluded packages were really removed
    assert shell(f"rpm -qi {excluded_pkg_1}").returncode == 1
    assert shell(f"rpm -qi {excluded_pkg_2}").returncode == 1
