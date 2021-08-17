import re

from collections import namedtuple
from pathlib import Path

import pytest

from envparse import env


def get_system_version(system_release_content=None):
    """Return a namedtuple with major and minor elements, both of an int type.

    Examples:
    Oracle Linux Server release 6.10
    Oracle Linux Server release 7.8
    CentOS release 6.10 (Final)
    CentOS Linux release 7.6.1810 (Core)
    CentOS Linux release 8.1.1911 (Core)
    """
    match = re.search(r".+?(\d+)\.(\d+)\D?", system_release_content)
    if not match:
        return "not match"
    version = namedtuple("Version", ["major", "minor"])(int(match.group(1)), int(match.group(2)))

    return version


def test_good_convertion(shell, convert2rhel):

    with open("/etc/system-release", "r") as file:
        system_release = file.read()
        system_version = get_system_version(system_release_content=system_release)
        if system_version.major == 7:
            dependency_pkgs = [
                "abrt-retrace-client",  # OAMG-4447
                "libreport-cli",  # OAMG-4447
                "ghostscript-devel",  # Case 02855547
                "python2-dnf",  # OAMG-4690
                "python2-dnf-plugins-core",  # OAMG-4690
                "redhat-lsb-trialuse",  # OAMG-4942
                "ldb-tools",  # OAMG-4941
                "python-requests",  # OAMG-4936
            ]
        elif system_version.major == 8:
            dependency_pkgs = [
                "python39-psycopg2-debug",  # OAMG-5239, OAMG-4944 - package not available on Oracle Linux 8
            ]

    # installing dependency packages
    assert shell("yum install -y {}".format(" ".join(dependency_pkgs))).returncode == 0

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Conversion successful!")

    assert c2r.exitstatus == 0
