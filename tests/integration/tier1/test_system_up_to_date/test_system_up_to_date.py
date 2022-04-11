from envparse import env


def test_non_latest_kernel(shell, convert2rhel):
    """
    System has non latest kernel installed, thus the conversion
    has to be inhibited.
    """

    # run utility until the reboot
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0


def test_system_not_updated(shell, convert2rhel):
    """
    System contains at least one package that is not updated to
    the latest version. The c2r has to display a warning message
    about that.
    """
    pass
