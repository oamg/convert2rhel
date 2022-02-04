def test_check_user_response(convert2rhel):

    # Run c2r registration with no username
    with convert2rhel("-y " "--no-rpm-va") as c2r:
        c2r.expect(" ... activation key not found, username and password required")
        c2r.expect("Username: ")
        c2r.sendline()
        if c2r.expect("Username: ") == 0:
            c2r.sendcontrol("d")
    assert c2r.exitstatus != 0

    # Run c2r registration with username but no password
    with convert2rhel("-y " "--no-rpm-va") as c2r:
        c2r.expect(" ... activation key not found, username and password required")
        c2r.expect("Username: ")
        c2r.sendline("foo")
        c2r.expect("Password: ")
        c2r.sendline()
        if c2r.expect("Password: ") == 0:
            c2r.sendcontrol("d")
    assert c2r.exitstatus != 0
