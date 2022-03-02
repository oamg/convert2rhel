from envparse import env


def test_remove_all_submgr_pkgs(shell, convert2rhel):
    """Test that all subscription-manager pkgs (no matter the signature) get removed.

    And that the system is unregistered before that.
    """

    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        # Check that the system is unregistered before removing the sub-mgr
        c2r.expect("Calling command 'subscription-manager unregister'")

        # Check that the pre-installed sub-mgr gets removed
        c2r.expect("Calling command 'rpm -e --nodeps subscription-manager'")
        # Just to make sure the above output appeared before installing the
        # subscription-manager pkgs
        c2r.expect("Installing subscription-manager RPMs.")

    assert c2r.exitstatus == 0

    # Check that the subscription-manager installed by c2r has the Red Hat signature
    assert (
        "199e2f91fd431d51"
        in shell(
            "rpm -q --qf '%|DSAHEADER?{%{DSAHEADER:pgpsig}}:"
            "{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{(none)}|}|' "
            "subscription-manager"
        ).output
    )
