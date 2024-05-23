import pytest


@pytest.mark.parametrize("satellite_registration", ["RHEL7_AND_CENTOS7_SAT_REG"], indirect=True)
@pytest.mark.test_one_key_satellite_conversion
def test_one_key_satellite_conversion(shell, convert2rhel, satellite_registration, remove_repositories):
    """
    Conversion method using the Satellite credentials for a registration.
    The system is pre-registered to the Satellite instance prior to the conversion.
    We use one activation key containing both the original OS and RHEL repositories.
    """
    # We need to enable the current system repositories prior to the conversion
    shell("subscription-manager repos --enable=*")

    with convert2rhel("-y --debug") as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
