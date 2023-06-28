import pytest

from conftest import SATELLITE_PKG_DST, SATELLITE_PKG_URL
from envparse import env


@pytest.mark.satellite_conversion
def test_satellite_conversion(shell, convert2rhel):
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
        "-y --no-rpm-va -k {} -o {} --debug".format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0
