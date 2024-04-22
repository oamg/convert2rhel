import re

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS


def test_single_yum_transaction(convert2rhel, shell):
    """Run the conversion using the single yum transaction.

    This will run the conversion up until the point of the single yum
    transaction package replacements.
    """
    pkgmanager = "yum"

    if re.match(r"^(centos|oracle|alma|rocky|stream)-8", SYSTEM_RELEASE_ENV):
        pkgmanager = "dnf"

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        c2r.expect("no modifications to the system will happen this time.", timeout=1200)
        c2r.expect("Successfully validated the %s transaction set." % pkgmanager, timeout=600)
        c2r.expect("This process may take some time to finish.", timeout=300)
        c2r.expect("System packages replaced successfully.", timeout=900)
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
