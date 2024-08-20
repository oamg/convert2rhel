import pytest

from conftest import TEST_VARS


@pytest.mark.parametrize("yum_conf_exclude", [["kernel*", "redhat-release-server"]], indirect=True)
def test_yum_conf_exclude_packages(convert2rhel, yum_conf_exclude):
    """
    Verify, the conversion does not raise:
    'Could not find any kernel from repositories to compare against the loaded kernel.'
    When `exclude=kernel kernel-core redhat-release-server` is defined in yum.conf
    Verify IS_LOADED_KERNEL_LATEST has succeeded is raised.
    Reference ticket: https://issues.redhat.com/browse/RHELC-774
    """
    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        c2r.expect("IS_LOADED_KERNEL_LATEST has succeeded")

    assert c2r.exitstatus == 0
