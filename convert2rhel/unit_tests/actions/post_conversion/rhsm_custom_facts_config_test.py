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

from convert2rhel import actions, subscription, utils
from convert2rhel.actions.post_conversion.rhsm_custom_facts_config import RHSMCustomFactsConfig


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class RunSubprocessMocked:
    def __call__(self, *args, **kwargs):
        return MockCompletedProcess()


class MockCompletedProcess:
    def __init__(self):
        self.returncode = 1


@pytest.fixture
def rhsm_custom_facts_config_instance():
    return RHSMCustomFactsConfig()


def test_rhsm_custom_facts_config(rhsm_custom_facts_config_instance, monkeypatch):
    # need to mock runsubprocess
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
    monkeypatch.setattr(
        subscription, "update_rhsm_custom_facts", mock.Mock(return_value=(1, "Unable to update RHSM custom facts"))
    )

    expected = {
        actions.ActionMessage(
            level="WARNING",
            title="FailedRHSMUpdateCustomFacts",
            id="UPDATE_RHSM_CUSTOM_FACTS",
            description="Failed to update the RHSM custom facts with return code: 1 and output: Unable to update RHSM custom facts.",
        )
    }

    rhsm_custom_facts_config_instance.run()

    assert expected.issuperset(rhsm_custom_facts_config_instance.messages)
    assert expected.issubset(rhsm_custom_facts_config_instance.messages)


def test_rhsm_custom_facts_config_no_output(rhsm_custom_facts_config_instance, monkeypatch, caplog):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
    monkeypatch.setattr(subscription, "update_rhsm_custom_facts", mock.Mock(return_value=(1, "")))

    rhsm_custom_facts_config_instance.run()

    # assert message in caplog.records[-1].message
