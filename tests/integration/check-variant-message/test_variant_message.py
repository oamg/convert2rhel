from envparse import env


def test_check_variant_message(convert2rhel):
    # Run c2r with --variant option
    with convert2rhel(
        ("--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug --variant Server").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("WARNING - The -v|--variant option is not supported anymore and has no effect")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
    assert c2r.exitstatus != 0

    # Run c2r with --variant option empty
    with convert2rhel(
        ("--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug --variant").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("WARNING - The -v|--variant option is not supported anymore and has no effect")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
    assert c2r.exitstatus != 0

    # Run c2r with -v option
    with convert2rhel(
        ("--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug -v Client").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("WARNING - The -v|--variant option is not supported anymore and has no effect")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
    assert c2r.exitstatus != 0

    # Run c2r with -v option empty
    with convert2rhel(
        ("--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug -v").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("WARNING - The -v|--variant option is not supported anymore and has no effect")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
    assert c2r.exitstatus != 0
