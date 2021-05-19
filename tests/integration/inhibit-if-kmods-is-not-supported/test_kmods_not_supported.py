from pathlib import Path

import pytest

from envparse import env


@pytest.mark.good_tests
def test_good_convertion(convert2rhel):
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Kernel modules are compatible.")
    assert c2r.exitstatus == 0


@pytest.mark.bad_tests
def test_bad_convertion(shell, insert_custom_kmod, convert2rhel):
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("The following kernel modules are not supported in RHEL")
    assert c2r.exitstatus == 1
