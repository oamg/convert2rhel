import platform


system_version = platform.platform()


def test_remove_excluded_pkgs_from_config(shell):
    """Remove some excluded packages from the CentOS Linux 7 config file.

    That means Convert2RHEL won't remove them before the main conversion transaction.
    """

    if "centos-7" in system_version:
        assert shell("sed -i '/mod_ldap/d' /usr/share/convert2rhel/configs/centos-7-x86_64.cfg").returncode == 0
        assert shell("sed -i '/mod_proxy_html/d' /usr/share/convert2rhel/configs/centos-7-x86_64.cfg").returncode == 0

        # make sure that the packages we don't want convert2rhel to remove are present on the test system
        assert shell("yum install mod_ldap mod_proxy_html -y").returncode == 0
