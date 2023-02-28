import re

from collections import namedtuple

import pytest


def get_system_version(system_release_content=None):
    """Return a namedtuple with major and minor elements, both of an int type.

    Examples:
    Oracle Linux Server release 7.8
    CentOS Linux release 7.6.1810 (Core)
    CentOS Linux release 8.1.1911 (Core)
    """
    match = re.search(r".+?(\d+)\.(\d+)\D?", system_release_content)
    if not match:
        return "not match"
    version = namedtuple("Version", ["major", "minor"])(int(match.group(1)), int(match.group(2)))

    return version


@pytest.mark.good_tests
def test_good_convertion_without_rhsm(shell, convert2rhel):
    """
    Test if --enablerepo are not skipped when  subscription-manager are disabled and test if repo passed are valid.
    """
    with open("/etc/system-release", "r") as file:
        system_release = file.read()
        system_version = get_system_version(system_release_content=system_release)
        if system_version.major == 7:
            enable_repo_opt = "--enablerepo rhel-7-server-rpms --enablerepo rhel-7-server-optional-rpms --enablerepo rhel-7-server-extras-rpms"
        elif system_version.major == 8:
            if system_version.minor in (4, 6):
                enable_repo_opt = (
                    "--enablerepo rhel-8-for-x86_64-baseos-eus-rpms --enablerepo rhel-8-for-x86_64-appstream-eus-rpms"
                )
            else:
                enable_repo_opt = (
                    "--enablerepo rhel-8-for-x86_64-baseos-rpms --enablerepo rhel-8-for-x86_64-appstream-rpms"
                )

    with convert2rhel("-y --no-rpm-va --disable-submgr {} --debug".format(enable_repo_opt)) as c2r:
        c2r.expect("The repositories passed through the --enablerepo option are all accessible.")
        # send Ctrl-C
        c2r.send(chr(3))


@pytest.mark.bad_tests
def test_bad_convertion_without_rhsm(shell, convert2rhel):
    """
    Test if --enablerepo are not skipped when  subscription-manager are disabled and test the convertion will stop
    with non-valid repo. Make sure that after failed repo check there is a kernel installed.
    """
    with convert2rhel("-y --no-rpm-va --disable-submgr --enablerepo fake-rhel-8-for-x86_64-baseos-rpms --debug") as c2r:
        c2r.expect(
            "CRITICAL - Unable to access the repositories passed through the --enablerepo option. "
            "For more details, see YUM/DNF output"
        )

    assert c2r.exitstatus == 1

    assert shell("rpm -qi kernel").returncode == 0
