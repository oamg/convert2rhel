# -*- coding: utf-8 -*-
#
# Copyright(C) 2024 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__metaclass__ = type


import pytest

from convert2rhel import unit_tests, utils
from convert2rhel.actions.system_checks import grub_validity
from convert2rhel.unit_tests import RunSubprocessMocked


@pytest.fixture
def grub_validity_instance():
    return grub_validity.GrubValidity()


@pytest.mark.parametrize(
    ("mkconfig_ret_code", "mkconfig_output"),
    (
        (0, "generated grub configuration"),
        (1, "reported errors"),
    ),
)
def test_grub_validity_error(grub_validity_instance, monkeypatch, mkconfig_ret_code, mkconfig_output, caplog):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_value=(mkconfig_output, mkconfig_ret_code)))
    grub_validity_instance.run()
    if mkconfig_ret_code != 0:
        unit_tests.assert_actions_result(
            grub_validity_instance,
            level="ERROR",
            id="INVALID_GRUB_FILE",
            title="/etc/default/grub invalid",
            description="The /etc/default/grub file seems to be invalid and must be fixed before continuing the"
            "conversion.",
            diagnosis="Calling grub2-mkconfig failed with:\n{}".format(mkconfig_output),
            remediations="Fix issues reported by the grub2-mkconfig utility and re-run the conversion.",
        )
    else:
        "No issues found with the /etc/default/grub file." in caplog.records[-1].message
