from __future__ import print_function

import fileinput
import os.path

import pytest

from conftest import TEST_VARS


target_line = "GRUB_CMDLINE_LINUX"


@pytest.fixture
def grub_file_invalid(shell, backup_directory):
    """
    Modify the /etc/default/grub file with 'invalid' changes.
    These changes should cause the 'grub2-mkfile' call to fail.
    The changes made to the grub file result into:
    5 GRUB_TERMINAL_OUTPUT="foo"
    6 GRUB_CMDLINE_LINUX
    7 GRUB_DISABLE_RECOVERY="bar"
    """
    grub_config = "/etc/default/grub"
    grub_config_bkp = os.path.join(backup_directory, "grub.bkp")

    # Backup the original file
    shell(f"cp {grub_config} {grub_config_bkp}")

    # Make invalid changes to the grub file
    for line in fileinput.FileInput(grub_config, inplace=True):
        if target_line in line:
            line = line.replace(line, target_line + "\n")
        print(line, end="")

    yield

    # Restore from backup
    shell(f"mv -f {grub_config_bkp} {grub_config}")


def test_invalid_changes_to_grub_file(convert2rhel, grub_file_invalid):
    """
    Validate that an error is raised, when the grub config file contains invalid values.
    """

    with convert2rhel(
        "analyze -y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        assert c2r.expect_exact("Prepare: Check if the grub file is valid") == 0
        assert (
            c2r.expect_exact("ERROR - (ERROR) GRUB_VALIDITY::INVALID_GRUB_FILE - Grub boot entry file is invalid") == 0
        )

    assert c2r.exitstatus == 2
