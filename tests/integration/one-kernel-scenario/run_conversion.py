from collections import namedtuple

import pytest


def test_run_conversion_using_custom_repos(shell, convert2rhel):

    with open("/etc/system-release", "r") as file:
        system_release = file.read()
        if "Oracle Linux Server release 7.9" in system_release:
            assert shell("yum remove -y python3").returncode == 0

    enable_repo_opt = "--enablerepo rhel-7-server-rpms --enablerepo rhel-7-server-optional-rpms --enablerepo rhel-7-server-extras-rpms"

    with convert2rhel("-y --no-rpm-va --disable-submgr {} --debug".format(enable_repo_opt)) as c2r:
        c2r.expect("Conversion successful!")

    assert c2r.exitstatus == 0
    if "Oracle Linux Server release 7.9" in system_release:
        assert shell("yum install -y python3 --enablerepo=*").returncode == 0
