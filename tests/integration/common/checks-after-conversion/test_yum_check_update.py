import pytest


@pytest.mark.parametrize("package", ["kernel"])
def test_yum_check_update(shell, package):
    """
    After the conversion verify yum check-update does not return outdated package.
    """
    assert package not in shell(f"yum check-update {package}").output
