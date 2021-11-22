from pathlib import Path

import pytest

from envparse import env


@pytest.fixture()
def insert_custom_kmod(shell):
    def factory():
        origin_kmod_loc = Path("/lib/modules/$(uname -r)/kernel/drivers/net/bonding/bonding.ko.xz")
        new_kmod_dir = origin_kmod_loc.parent / "custom_module_location"

        shell(f"mkdir {new_kmod_dir.as_posix()}")
        shell(f"mv {origin_kmod_loc.as_posix()} {new_kmod_dir.as_posix()}")
        shell("depmod")
        shell(f"modprobe bonding -v")

    return factory


def test_inhibit_if_custom_module_loaded(insert_custom_kmod, convert2rhel):
    insert_custom_kmod()
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("The following kernel modules are not supported in RHEL")
    assert c2r.exitstatus != 0


def test_do_not_inhibit_if_module_is_not_loaded(shell, convert2rhel):
    assert shell("modprobe -r -v bonding").returncode == 0
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Kernel modules are compatible.")
        c2r.send(chr(3))
    assert c2r.exitstatus != 0
