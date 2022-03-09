import platform

from envparse import env


def test_no_sub_manager_installed(shell, convert2rhel):
    """Test that no subscription manager is installed and the conversion
    is able to get to the last point of the rollback.

    """

    assert shell("yum remove -y subscription-manager").returncode == 0

    with convert2rhel(
        ("--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")
        # On OracleLinux8 there is one question less than on other distros
        if "oracle-8" not in platform.platform():
            c2r.expect("Continue with the system conversion?")
            c2r.sendline("y")
        c2r.expect("The subscription-manager package is not installed.")
        c2r.expect("No packages related to subscription-manager installed.")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")
        c2r.expect("The tool allows rollback of any action until this point.")
        c2r.sendline("n")
