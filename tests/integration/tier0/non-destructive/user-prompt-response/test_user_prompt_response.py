import pytest

from envparse import env


@pytest.mark.test_empty_username_and_password
def test_check_user_response_user_and_password(convert2rhel):
    """
    Run c2r registration with no username and password provided.
    Verify that user has to pass non empty username/password string to continue, otherwise enforce the input prompt again.
    """
    with convert2rhel("-y --serverurl {}".format(env.str("RHSM_SERVER_URL")), unregister=True) as c2r:
        c2r.expect(" ... activation key not found, username and password required")
        c2r.expect("Username")
        c2r.sendline()
        # Assert the prompt loops and returns "Username:"
        # when the input is empty, hence the '0' index.
        # In case the loop doesn't work, the prompt returns
        # "Password" and raises the assertion error.
        assert c2r.expect("Username", timeout=300) == 0
        # Provide username, expect password prompt

        retries = 0
        while True:
            c2r.sendline(env.str("RHSM_USERNAME"))
            print("Sending username:", env.str("RHSM_USERNAME"))
            c2r.expect("Password: ")
            c2r.sendline()
            try:
                assert c2r.expect("Password", timeout=300) == 0
                # Provide password, expect successful registration and subscription prompt
                c2r.sendline(env.str("RHSM_PASSWORD"))
                print("Sending password")
                assert c2r.expect("System registration succeeded", timeout=180) == 0
                break
            except Exception:
                retries = retries + 1
                if retries == 3:
                    raise
                continue

        c2r.sendcontrol("c")
    assert c2r.exitstatus != 0
