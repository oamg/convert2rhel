import pytest

from conftest import SATELLITE_PKG_DST, SATELLITE_PKG_URL
from envparse import env


@pytest.mark.test_satellite_conversion
def test_satellite_conversion(shell, convert2rhel):
    """
    Conversion method using the Satellite credentials for registration.
    The subscription-manager package is removed for this conversion method.
    The katello-ca-consumer package is installed from the Satellite server.
    """
    # Remove subscription manager if installed
    assert shell("yum remove subscription-manager -y").returncode == 0

    assert shell("yum install wget -y").returncode == 0

    assert (
        shell(
            "wget --no-check-certificate --output-document {} {}".format(SATELLITE_PKG_DST, SATELLITE_PKG_URL)
        ).returncode
        == 0
    )

    with convert2rhel(
        "-y -k {} -o {} --debug".format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0
