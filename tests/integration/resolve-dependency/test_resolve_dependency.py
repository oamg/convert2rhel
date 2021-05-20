from pathlib import Path

import pytest

from envparse import env


def test_good_convertion(shell, convert2rhel):

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
