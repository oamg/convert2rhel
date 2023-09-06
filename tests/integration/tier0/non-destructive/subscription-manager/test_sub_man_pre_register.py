import pytest

from envparse import env


@pytest.mark.test_pre_registered_wont_unregister
def test_pre_registered_wont_unregister(shell, pre_registered, disabled_telemetry, convert2rhel):
    """
    This test verifies that running conversion on pre-registered system won't unregister the system.
    1. Install subscription-manager, download the SSL certificate
    2. Register with subscription-manager and attach a subscription using the pool
    (both handled by the pre_registered fixture)
    3. Run convert2rhel without provided credentials
    4. Exit at the point of no return.
    5. Verify that convert2rhel won't unregister the system at any point and the UUID is same before and after the run.
    """
    with convert2rhel("--debug --no-rpm-va") as c2r:
        c2r.expect("Subscription Manager is already present", timeout=300)
        c2r.expect(
            "WARNING - No rhsm credentials given to subscribe the system. Skipping the subscription step", timeout=300
        )
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus != 0


@pytest.mark.test_pre_registered_re_register
def test_pre_registered_re_register(shell, pre_registered, disabled_telemetry, convert2rhel):
    """
    This test verifies that running conversion on pre-registered system and providing convert2rhel
    with credentials, will re-register the system.
    1. Install subscription-manager, download the SSL certificate
    2. Register with subscription-manager and attach a subscription using the pool
    (both handled by the pre_registered fixture)
    3. Run convert2rhel with provided credentials
    4. Verify that convert2rhel re-registered the system
    4. Exit at the point of no return.
    5. Verify that the system is still registered with the pre-registered system UUID.
    """
    with convert2rhel(
        "--debug --no-rpm-va --serverurl {} --username {} --password {}".format(
            env.str("RHSM_SERVER_URL"), env.str("RHSM_USERNAME"), env.str("RHSM_PASSWORD")
        )
    ) as c2r:

        c2r.expect("Registering the system using subscription-manager")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")
        c2r.expect("System unregistered successfully.", timeout=120)

    assert c2r.exitstatus != 0
    assert "This system is not yet registered" in shell("subscription-manager identity").output


@pytest.mark.test_unregistered_no_credentials
def test_unregistered_no_credentials(shell, convert2rhel, disabled_telemetry):
    """
    This test verifies that conversion fails when the system is not pre-registered
    and credentials are not provided to the convert2rhel command.
    Expected ERROR: SUBSCRIBE_SYSTEM::SYSTEM_NOT_REGISTERED - Not registered with RHSM
    """
    with convert2rhel("--debug --no-rpm-va") as c2r:

        c2r.expect("SUBSCRIBE_SYSTEM::SYSTEM_NOT_REGISTERED - Not registered with RHSM", timeout=300)

    assert c2r.exitstatus != 0
