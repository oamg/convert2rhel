from envparse import env


def test_check_user_response(convert2rhel):

    # Run c2r registration with no username and password provided
    # check for user prompt enforcing input, then continue with registration
    with convert2rhel(
        "-y --no-rpm-va --serverurl {}".format(
            env.str("RHSM_SERVER_URL"),
        )
    ) as c2r:
        c2r.expect(" ... activation key not found, username and password required")
        c2r.expect("Username: ")
        c2r.sendline()
        assert c2r.expect("Username: ") == 0
        # Provide username, expect password prompt
        c2r.sendline(env.str("RHSM_USERNAME"))
        c2r.expect("Password: ")
        c2r.sendline()
        assert c2r.expect("Password: ") == 0
        # Provide password, expect registration
        c2r.sendline(env.str("RHSM_PASSWORD"))
        assert c2r.expect("Registering the system using subscription-manager ...") == 0
        assert c2r.expect("Enter number of the chosen subscription: ") == 0
        c2r.sendcontrol("d")
    assert c2r.exitstatus != 0
