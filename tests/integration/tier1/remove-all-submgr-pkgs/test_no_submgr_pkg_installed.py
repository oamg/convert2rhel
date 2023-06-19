from envparse import env


def test_no_sub_manager_installed(shell, convert2rhel):
    """
    Verify the case when no subscription manager is installed and the conversion
    is able to get to the last point of the rollback.
    """

    packages_to_remove = ["subscription-manager", "python3-syspurpose"]
    for package in packages_to_remove:
        if package in shell(f"rpm -qi {package}").output:
            assert shell(f"yum remove -y {package}").returncode == 0

    with convert2rhel(
        "--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        assert c2r.expect("The subscription-manager package is not installed.", timeout=300) == 0
        assert c2r.expect("No packages related to subscription-manager installed.", timeout=300) == 0

        c2r.sendcontrol("c")
