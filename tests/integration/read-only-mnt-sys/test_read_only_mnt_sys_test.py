import pytest

from envparse import env


@pytest.mark.sys_ro
def test_readonly_sys(shell, capsys):
    convertion = shell(
        command=[
            (
                "convert2rhel -y "
                "--serverurl {} --username {} "
                "--password {} --pool {} "
                "--debug"
            ).format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
                env.str("RHSM_POOL"),
            )
        ]
    )
    out, err = capsys.readouterr()
    assert (
        "Stopping conversion due to read-only mount to "
        "/sys directory" in out
    )
    assert convertion.returncode == 1


@pytest.mark.mnt_ro
def test_readonly_mnt(shell, capsys):
    convertion = shell(
        command=[
            (
                "convert2rhel -y "
                "--serverurl {} --username {} "
                "--password {} --pool {} "
                "--debug"
            ).format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
                env.str("RHSM_POOL"),
            )
        ]
    )
    out, err = capsys.readouterr()
    assert (
        "Stopping conversion due to read-only mount to "
        "/mnt directory" in out
    )
    assert convertion.returncode == 1
