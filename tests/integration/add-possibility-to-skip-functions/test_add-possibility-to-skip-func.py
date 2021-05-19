from envparse import env


def test_skipping_functions_messaging(convert2rhel, monkeypatch):
    """Test just messaging."""
    monkeypatch.setenv("CONVERT2RHEL_UNSUPPORTED", "1")
    monkeypatch.setenv("CONVERT2RHEL_DEVEL_SKIP", "tainted_kernel,")
    with convert2rhel(
        f"-y "
        f"--no-rpm-va "
        f"--serverurl {env.str('RHSM_SERVER_URL')} "
        f"--username {env.str('RHSM_USERNAME')} "
        f"--password {env.str('RHSM_PASSWORD')} "
        f"--pool {env.str('RHSM_POOL')} "
        f"--debug"
    ) as c2r:
        c2r.expect("CONVERT2RHEL_UNSUPPORTED has been detected")
        c2r.expect("specified to be skipped")
        c2r.send(chr(3))


def test_skipping_functions_works(convert2rhel, insert_custom_kmod, monkeypatch):
    """Test that conversion passed with custom kmod but skipped kmod check."""
    monkeypatch.setenv("CONVERT2RHEL_UNSUPPORTED", "1")
    monkeypatch.setenv("CONVERT2RHEL_DEVEL_SKIP", "kmods_check,")
    with convert2rhel(
        f"-y "
        f"--no-rpm-va "
        f"--serverurl {env.str('RHSM_SERVER_URL')} "
        f"--username {env.str('RHSM_USERNAME')} "
        f"--password {env.str('RHSM_PASSWORD')} "
        f"--pool {env.str('RHSM_POOL')} "
        f"--debug"
    ) as c2r:
        c2r.expect("CONVERT2RHEL_UNSUPPORTED has been detected")
        c2r.expect("specified to be skipped")
    assert c2r.exitstatus == 0
