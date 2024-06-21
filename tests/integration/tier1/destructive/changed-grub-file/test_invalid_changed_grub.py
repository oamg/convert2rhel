from __future__ import print_function

import fileinput

from conftest import TEST_VARS


target_line = "GRUB_CMDLINE_LINUX"


def test_invalid_changes_to_grub_file(convert2rhel):
    """
    Modify the /etc/default/grub file with 'invalid' changes.
    These changes should cause the 'grub2-mkfile' call to fail.
    The changes made to the grub file result into:
    5 GRUB_TERMINAL_OUTPUT="foo"
    6 GRUB_CMDLINE_LINUX
    7 GRUB_DISABLE_RECOVERY="bar"
    """
    for line in fileinput.FileInput("/etc/default/grub", inplace=True):
        if target_line in line:
            line = line.replace(line, target_line + "\n")
        print(line, end="")

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        assert c2r.expect("GRUB2 config file generation failed.") == 0
    assert c2r.exitstatus == 0
