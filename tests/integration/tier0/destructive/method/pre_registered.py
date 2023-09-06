import pytest


@pytest.mark.test_pre_registered_conversion
def test_run_conversion_pre_registered(convert2rhel, pre_registered):
    with convert2rhel("-y --no-rpm-va --debug") as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
