def test_pre_registered_system_conversion(convert2rhel, pre_registered):
    with convert2rhel("-y --debug") as c2r:
        c2r.expect("Conversion successful!")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")
    assert c2r.exitstatus == 0
