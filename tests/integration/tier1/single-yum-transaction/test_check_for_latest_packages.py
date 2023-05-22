from conftest import SYSTEM_RELEASE_ENV
from envparse import env


PACKAGES_TO_VERIFY_RHEL_7 = [("shim-x64", "shim-x64-15.6-3.el7_9.x86_64")]
# Match the latest version used for conversion, currently Oracle Linux 8.7
PACKAGES_TO_VERIFY_RHEL_8_X = [("shim-x64", "shim-x64-15.6-1.el8.x86_64")]
# Mainly for CentOS Linux 8.5
PACKAGES_TO_VERIFY_RHEL_8_5 = [("shim-x64", "shim-x64-15.4-2.el8_1.x86_64")]


def test_packages_upgraded_after_conversion(convert2rhel, shell):
    """."""

    # Run utility until the reboot
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

    packages_to_verify = PACKAGES_TO_VERIFY_RHEL_7

    if "centos-8" in SYSTEM_RELEASE_ENV:
        packages_to_verify = PACKAGES_TO_VERIFY_RHEL_8_5
    elif "oracle-8" in SYSTEM_RELEASE_ENV:
        packages_to_verify = PACKAGES_TO_VERIFY_RHEL_8_X

    cmd = "rpm -q %s"
    for package, latest_version in packages_to_verify:
        assert shell(cmd % package).output == latest_version
