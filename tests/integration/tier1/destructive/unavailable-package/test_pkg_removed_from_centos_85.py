import pytest

from envparse import env


@pytest.mark.test_package_removed_from_centos_85
def test_removed_pkg_from_centos_85(convert2rhel, shell):
    """
    Verify that Convert2RHEL can correctly handle removal of package from the
    excluded list that is listed under the configuration files. This test
    installs the package that need to be removed during the plan preparation phase
    using an ansible playbook.
    The test itself verifies the presence of the package on the system
    and proceeds with the conversion.
    """
    assert shell("rpm -qi subscription-manager-initial-setup-addon").returncode == 0

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
