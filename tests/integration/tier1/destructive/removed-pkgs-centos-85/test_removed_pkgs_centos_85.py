from envparse import env


def test_removed_pkgs_centos_85(convert2rhel, shell):
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
