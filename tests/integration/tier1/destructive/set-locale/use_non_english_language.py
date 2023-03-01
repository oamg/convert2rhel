import re

from conftest import SYSTEM_RELEASE_ENV


def test_use_non_english_language(shell):
    """
    We need to test the ability of convert2rhel to convert the system when non english
    language is set (using non ascii language).
    Ref bug: https://bugzilla.redhat.com/show_bug.cgi?id=2022854
    """
    # install Chinese language pack for CentOS-8 and Oracle Linux 8

    if re.match(r"^(centos|oracle|alma|rocky)-8", SYSTEM_RELEASE_ENV):
        assert shell("dnf install glibc-langpack-zh -y").returncode == 0

    # set locale variables that affect translations to Chinese
    assert shell("localectl list-locales | grep zh_CN.utf8").returncode == 0
    assert shell("localectl set-locale LANG=zh_CN.utf8 LC_MESSAGES=zh_CN.utf8 LANGUAGE=zh_CN").returncode == 0

    # Testing farm is returning an error on CentOS7 mentioning
    # setting incompatible LC_CTYPE C.UTF-8.
    # However, the C.UTF-8 was added on RHEL-8 like distros.
    if "centos-7" in SYSTEM_RELEASE_ENV:
        assert shell("localectl set-locale LC_CTYPE=zh_CN.utf8").returncode == 0
