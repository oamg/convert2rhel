from conftest import TEST_VARS, SystemInformationRelease


def test_yum_conf_patch(convert2rhel, shell):
    """Test the scenario in which the user modifies /etc/yum.conf before the conversion.
    In that case during the conversion the config file does not get replaced with the config file from the RHEL package
    (%config(noreplace)) and we need to make sure that we patch the config file to get rid of the distroverpkg config
    key. Leaving the distroverpkg key there would lead to errors when calling yum after the conversion for not
    expanding the $releasever variable properly.
    """
    shell("echo '#random text' >> /etc/yum.conf")
    pkgmanager_conf = "/etc/yum.conf"
    if SystemInformationRelease.version.major >= 8:
        pkgmanager_conf = "/etc/dnf/dnf.conf"

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        c2r.expect("{} patched.".format(pkgmanager_conf))
    assert c2r.exitstatus == 0

    # The tsflags will prevent updating the RHEL-8.5 versions to RHEL-8.6
    assert shell("yum update -y -x convert2rhel --setopt tsflags=test").returncode == 0
