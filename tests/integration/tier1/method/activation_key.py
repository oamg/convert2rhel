from envparse import env


def test_activation_key_conversion(convert2rhel):
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} -k {} -o {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_KEY"),
            env.str("RHSM_ORG"),
        )
    ) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
