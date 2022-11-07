from envparse import env


def test_rhsm_non_eus_account(convert2rhel):
    """
    Verify that Convert2RHEL is working properly when non-eus repository is available
    for 8.4, 8.6, ... (EUS systems) and that after the conversion we have the correct
    repositories attached to the system.
    """

    # Mark the system so the check for the enabled repos after the conversion handles this special case
    with open('/non_eus_repos_used', mode='a'): pass

    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_NON_EUS_POOL"),
        )
    ) as c2r:
        c2r.expect("WARNING - rhel-8-for-x86_64-baseos-eus-rpms repository is not available")
        c2r.expect("WARNING - rhel-8-for-x86_64-appstream-eus-rpms repository is not available")
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
