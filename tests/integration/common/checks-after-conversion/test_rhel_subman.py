def test_rhel_subscription_manager(shell):
    """
    After conversion check.
    Verify that the subscription-manager installed by c2r has the Red Hat signature/
    """
    assert (
        "199e2f91fd431d51"
        in shell(
            "rpm -q --qf '%|DSAHEADER?{%{DSAHEADER:pgpsig}}:"
            "{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{(none)}|}|' "
            "subscription-manager"
        ).output
    )
