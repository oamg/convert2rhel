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
import six

from convert2rhel import actions, utils
from convert2rhel.actions.conversion import lock_releasever
from convert2rhel.systeminfo import Version, system_info
from convert2rhel.unit_tests import RunSubprocessMocked
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))

from convert2rhel import unit_tests


@pytest.fixture
def lock_releasever_in_rhel_repositories_instance():
    return lock_releasever.LockReleaseverInRHELRepositories()


@pytest.mark.parametrize(
    ("subprocess", "expected"),
    (
        (("output", 0), "RHEL repositories locked"),
        (("output", 1), "Locking RHEL repositories failed"),
    ),
)
@centos8
def test_lock_releasever_in_rhel_repositories(
    lock_releasever_in_rhel_repositories_instance, subprocess, expected, monkeypatch, caplog, pretend_os
):
    cmd = ["subscription-manager", "release", "--set=%s" % system_info.releasever]
    run_subprocess_mock = RunSubprocessMocked(
        side_effect=unit_tests.run_subprocess_side_effect(
            (cmd, subprocess),
        )
    )
    version = Version(8, 6)
    monkeypatch.setattr(system_info, "version", version)
    monkeypatch.setattr(
        utils,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(system_info, "eus_system", value=True)
    lock_releasever_in_rhel_repositories_instance.run()

    assert expected in caplog.records[-1].message
    assert run_subprocess_mock.call_count == 1


def test_lock_releasever_in_rhel_repositories_not_eus(lock_releasever_in_rhel_repositories_instance, caplog):
    lock_releasever_in_rhel_repositories_instance.run()
    assert "Skipping locking RHEL repositories to a specific EUS minor version." in caplog.records[-1].message
    assert expected.issuperset(lock_releasever_in_rhel_repositories_instance.messages)
    assert expected.issubset(lock_releasever_in_rhel_repositories_instance.messages)
