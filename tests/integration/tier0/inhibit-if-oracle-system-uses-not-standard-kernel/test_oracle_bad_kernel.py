from envparse import env


def test_bad_conversion(convert2rhel):
    """
    Verify that the check for compatible kernel on Oracle Linux works.
    Install unsupported kernel and run the conversion.
    Expect the warning message and c2r unsuccessful exit.
    """
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("The booted kernel version is incompatible", timeout=300)
    assert c2r.exitstatus == 1
