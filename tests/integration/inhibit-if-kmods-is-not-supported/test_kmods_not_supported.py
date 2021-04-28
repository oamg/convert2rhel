import pytest


try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path

from envparse import env


@pytest.mark.good_tests
def test_good_convertion(shell):
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
    assert convertion.returncode == 0


@pytest.fixture()
def insert_custom_kmod(shell):
    def factory():
        origin_kmod_loc = Path(
            "/lib/modules/$(uname -r)/"
            "kernel/drivers/net/bonding/bonding.ko.xz"
        )
        new_kmod_dir = origin_kmod_loc.parent / "custom_module_location"

        shell(command=["mkdir {new_loc}".format(new_loc=str(new_kmod_dir))])
        shell(
            command=[
                "mv {origin_kmod} {new_loc}".format(
                    origin_kmod=str(origin_kmod_loc),
                    new_loc=str(new_kmod_dir / origin_kmod_loc.name),
                )
            ]
        )
        shell(
            command=[
                "insmod {}".format(str(new_kmod_dir / origin_kmod_loc.name))
            ]
        )

    return factory


@pytest.mark.bad_tests
def test_bad_convertion(shell, insert_custom_kmod):
    insert_custom_kmod()
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


@pytest.mark.skip_check
@pytest.mark.skip   # feature is not yet added - skipping
def test_skip_kmod_check(shell, insert_custom_kmod):
    insert_custom_kmod()
    convertion = shell(
        command=[
            (
                "convert2rhel -y "
                "--serverurl {} --username {} "
                "--password {} --pool {} "
                "--no-kmods-check "
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
    assert convertion.returncode == 0
