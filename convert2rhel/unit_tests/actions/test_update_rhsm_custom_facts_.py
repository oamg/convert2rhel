# Copyright(C) 2023 Red Hat, Inc.
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
import six

from convert2rhel import actions, utils
from convert2rhel.actions.post_conversion.failed_to_update_rhsm_custom_facts import UpdateRHSMCustomFacts
from convert2rhel.unit_tests import RunSubprocessMocked


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def update_rhsm_custom_facts_instance():
    return UpdateRHSMCustomFacts()


@mock.patch("convert2rhel.toolopts.tool_opts.no_rhsm", False)
def test_update_rhsm_custom_fatcs_failure(update_rhsm_custom_facts_instance, monkeypatch):
    # need to mock runsubprocess
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

    # here is the message expected
    diagnosis = "Failed to update the RHSM custom facts with return code 'whatever return code is' and output 'whatever output is'."

    update_rhsm_custom_facts_instance.run()

    excepted = set((actions.ActionMessage(level="WARNING", id="", description="", diagnosis=None)))

    assert excepted.issuperset(update_rhsm_custom_facts_instance.message)
    assert excepted.issubset(update_rhsm_custom_facts_instance.message)
