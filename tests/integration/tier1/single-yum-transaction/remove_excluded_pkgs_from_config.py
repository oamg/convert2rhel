import platform


system_version = platform.platform()


def test_remove_excluded_pkgs_from_config(shell):
    """Remove some packages from the config file."""

    if "centos-7" in system_version:
        # TODO(r0x0d): Probably we can run this in just one sed command?
        assert shell("sed -i '/mod_ldap/d' /usr/share/convert2rhel/configs/centos-7-x86_64.cfg").returncode == 0
        assert shell("sed -i '/mod_proxy_html/d' /usr/share/convert2rhel/configs/centos-7-x86_64.cfg").returncode == 0

    assert shell("yum install mod_ldap mod_proxy_html -y").returncode == 0
