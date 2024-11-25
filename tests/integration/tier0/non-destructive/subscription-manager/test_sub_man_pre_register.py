import pytest

from conftest import TEST_VARS


def test_pre_registered_wont_unregister(shell, pre_registered, convert2rhel):
    """
    This test verifies that running conversion on pre-registered system won't unregister the system.
    1. Install subscription-manager, download the SSL certificate
    2. Register with subscription-manager and attach a subscription using the pool
    (both handled by the pre_registered fixture)
    3. Run convert2rhel without provided credentials
    4. Exit at the point of no return.
    5. Verify that convert2rhel won't unregister the system at any point and the UUID is same before and after the run.
    """
    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Subscription Manager is already present", timeout=300)
        c2r.expect(
            "The SUBSCRIBE_SYSTEM action has succeeded.",
            timeout=600,
        )
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus == 1


def test_pre_registered_re_register(shell, pre_registered, convert2rhel):
    """
    This test verifies that running conversion on pre-registered system and providing convert2rhel
    with credentials, will re-register the system.
    1. Install subscription-manager, download the SSL certificate
    2. Register with subscription-manager and attach a subscription using the pool
    (both handled by the pre_registered fixture)
    3. Run convert2rhel with provided credentials
    4. Verify that convert2rhel re-registered the system
    4. Exit at the point of no return.
    """
    with convert2rhel(
        "--debug --serverurl {} --username {} --password {}".format(
            TEST_VARS["RHSM_SERVER_URL"], TEST_VARS["RHSM_SCA_USERNAME"], TEST_VARS["RHSM_SCA_PASSWORD"]
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Registering the system using subscription-manager")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
        c2r.expect("System unregistered successfully.", timeout=120)

    assert c2r.exitstatus == 1
    assert "This system is not yet registered" in shell("subscription-manager identity").output


def test_unregistered_no_credentials(shell, convert2rhel):
    """
    This test verifies that conversion fails when the system is not pre-registered
    and credentials are not provided to the convert2rhel command.
    Expected ERROR: SUBSCRIBE_SYSTEM::SYSTEM_NOT_REGISTERED - Not registered with RHSM
    """
    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("SUBSCRIBE_SYSTEM::SYSTEM_NOT_REGISTERED - Not registered with RHSM", timeout=300)

    assert c2r.exitstatus == 2


@pytest.mark.parametrize("pre_registered", [("RHSM_USERNAME", "RHSM_PASSWORD")], indirect=True)
def test_no_sca_not_subscribed(shell, pre_registered, convert2rhel):
    """
    This test verifies that running conversion on pre-registered system
    without an attached subscription will try auto attaching the subscription.
    SCA disabled account is used for this scenario.
    """
    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("We'll try to auto-attach a subscription")
        c2r.expect("The SUBSCRIBE_SYSTEM action has succeeded.")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus == 1

    assert "No consumed subscription pools were found" in shell("subscription-manager list --consumed").output


@pytest.mark.parametrize("pre_registered", [("RHSM_NOSUB_USERNAME", "RHSM_NOSUB_PASSWORD")], indirect=True)
def test_no_sca_subscription_attachment_error(shell, convert2rhel, pre_registered):
    """
    This test verifies that running conversion on pre-registered system
    without an attached subscription will try auto attaching the subscription.
    When the attachment fails, the SUBSCRIBE_SYSTEM::NO_ACCESS_TO_RHEL_REPOS
    error is raised.
    We're deliberately using SCA disabled account without any available subscriptions for this scenario.
    """
    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("We'll try to auto-attach a subscription")
        c2r.expect_exact("(ERROR) SUBSCRIBE_SYSTEM::NO_ACCESS_TO_RHEL_REPOS - No access to RHEL repositories")

    assert c2r.exitstatus == 2
