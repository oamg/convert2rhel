from __future__ import print_function

import fileinput

from envparse import env


targetline = "GRUB_CMDLINE_LINUX"


def test_modify_grub_valid(convert2rhel):
    blockcmt = "\n# comment added by test\n"
    inlinecmt_post = "# comment added by test"
    whitespace = "     "
    for line in fileinput.FileInput("/etc/default/grub", inplace=True):
        if targetline in line:
            line = line.replace("\n", "")
            line = line.replace(
                line,
                blockcmt + whitespace + line + whitespace + inlinecmt_post + blockcmt + "\n",
            )
        print(line, end="")

    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        assert c2r.expect("Successfully updated GRUB2 on the system.") == 0
    assert c2r.exitstatus == 0
