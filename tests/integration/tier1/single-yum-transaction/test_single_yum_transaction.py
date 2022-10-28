import platform

from envparse import env


system_version = platform.platform()


def test_single_yum_transaction(convert2rhel, shell):
    """Run the conversion using the single yum transaction.

    This will run the conversion up until the point of the single yum
    transaction package replacements.
    """
    pkgmanager = "yum"

    if "centos-8" in system_version or "oracle-8" in system_version:
        pkgmanager = "dnf"

    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("no modifications to the system will happen this time.", timeout=900)
        c2r.expect("Successfully validated the %s transaction set." % pkgmanager, timeout=600)
        c2r.expect("This process may take some time to finish.", timeout=300)
        c2r.expect("System packages replaced successfully.", timeout=900)
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
