import pytest

from envparse import env


@pytest.mark.test_packages_upgraded_after_conversion
def test_packages_upgraded_after_conversion(convert2rhel, shell):
    """
    Verify that packages get correctly reinstalled and not
    downgraded during the conversion.
    """

    checked_packages = ["shim-x64"]

    packages_to_verify = {}

    for package in checked_packages:
        latest_version = shell(f"repoquery --quiet {package}").output.strip("\n")
        is_installed = shell(f"rpm -q {package}").output
        if "is not installed" in is_installed:
            shell(f"yum install -y {package}")
        if latest_version:
            packages_to_verify[package] = latest_version

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

    for package, latest_version in packages_to_verify.items():
        assert (
            shell(
                f"rpm -q --queryformat='%{{name}}-%{{epoch}}:%{{version}}-%{{release}}.%{{arch}}' {package}"
            ).output.strip("\n")
            == latest_version
        )
