from __future__ import print_function

import fileinput

from envparse import env


targetline = "GRUB_CMDLINE_LINUX"


def test_modify_grub_invalid(convert2rhel):
    for line in fileinput.FileInput("/etc/default/grub", inplace=True):
        if targetline in line:
            line = line.replace(line, targetline + "\n")
        print(line, end="")

    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        assert c2r.expect("GRUB2 config file generation failed.") == 0
    assert c2r.exitstatus == 0
