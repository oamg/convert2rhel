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


def test_grub_validity_error(grub_validity_instance, monkeypatch):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_value=("output", 127)))
    grub_validity_instance.run()
    unit_tests.assert_actions_result(
        grub_validity_instance,
        level="ERROR",
        id="INVALID_GRUB_FILE",
        title="Grub boot entry file is invalid",
        description="The grub file seems to be invalid leaving the system in a"
        " non-clean state and must be fixed before continuing the conversion"
        " to ensure a smooth process.",
        remediations="Check the grub file inside `/etc/default` directory and remove any "
        "misconfigurations, then re-run the conversion.",
    )
