import pytest


try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path

from envparse import env


@pytest.mark.good_tests
def test_good_conversion(shell, capsys):
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
    # TODO make unregistering automatically, i.e. create a yield fixture to run
    #   convert2rhel with the rhsm
    shell("subscription-manager unregister")
    assert convertion.returncode == 0
    stdout, _ = capsys.readouterr()
    assert "Kernel is compatible with RHEL" in stdout


@pytest.mark.bad_tests
def test_bad_conversion(shell, capsys):
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
    shell("subscription-manager unregister")
    assert convertion.returncode == 1
    stdout, _ = capsys.readouterr()
    assert (
        "The booted kernel version is incompatible"
        in stdout
    )
