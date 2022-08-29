from envparse import env


def test_check_user_response_user_and_password(convert2rhel):
    """
    Run c2r registration with no username and password provided
    check for user prompt enforcing input, then continue with registration.
    """
    with convert2rhel("-y --no-rpm-va --serverurl {}".format(env.str("RHSM_SERVER_URL")), unregister=True) as c2r:
        c2r.expect_exact(" ... activation key not found, username and password required")
        c2r.expect_exact("Username")
        c2r.sendline()
        # Assert the prompt loops and returns "Username:"
        # when the input is empty, hence the '0' index.
        # In case the loop doesn't work, the prompt returns
        # "Password" and raises the assertion error.
        assert c2r.expect_exact(["Username", "Password"], timeout=300) == 0
        # Provide username, expect password prompt
        c2r.sendline(env.str("RHSM_USERNAME"))
        c2r.expect_exact("Password: ")
        c2r.sendline()
        assert c2r.expect_exact(["Password", "Enter number of the chosen subscription"], timeout=300) == 0
        # Provide password, expect successful registration and subscription prompt
        c2r.sendline(env.str("RHSM_PASSWORD"))
        c2r.expect_exact("Enter number of the chosen subscription: ")
        # Due to inconsistent behavior of Ctrl+c
        # the Ctrl+d is used to terminate the process instead
        c2r.sendcontrol("d")
    assert c2r.exitstatus != 0


def test_check_user_response_organization(convert2rhel):
    """
    Run c2r registration with activation key provided and check for user prompt while organization left blank.
    """
    substitute_org = "foo"
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} -k {}".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_KEY"),
        ),
        unregister=True,
    ) as c2r:
        c2r.expect_exact("activation key detected")
        c2r.expect_exact("Organization: ")
        c2r.sendline()
        assert c2r.expect_exact(["Organization", "Registering the system"], timeout=300) == 0
        c2r.sendline(substitute_org)
        c2r.expect_exact("Registering the system using subscription-manager ...")
        # Due to inconsistent behavior of Ctrl+c
        # the Ctrl+d is used to terminate the process instead
        c2r.sendcontrol("d")
    assert c2r.exitstatus != 0


def test_auto_attach_pool_submgr(convert2rhel):
    """
    Provide Convert2RHEL with username and password with just one subscription available.
    Check that the subscription is automatically selected.
    """
    single_pool_id = env.str("RHSM_SINGLE_SUB_POOL")
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_SINGLE_SUB_USERNAME"),
            env.str("RHSM_SINGLE_SUB_PASSWORD"),
        ),
        unregister=True,
    ) as c2r:
        c2r.expect(
            f"{single_pool_id} is the only subscription available, it will automatically be selected for the conversion."
        )
        c2r.sendcontrol("d")

        assert c2r.exitstatus != 0
