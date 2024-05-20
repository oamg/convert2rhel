# -*- coding: utf-8 -*-
#
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

from convert2rhel import actions, systeminfo, unit_tests, utils
from convert2rhel.actions.system_checks import duplicate_packages
from convert2rhel.systeminfo import Version, system_info
from convert2rhel.unit_tests import RunSubprocessMocked
from convert2rhel.unit_tests.conftest import all_systems


@pytest.fixture
def duplicate_packages_action():
    return duplicate_packages.DuplicatePackages()


@pytest.mark.parametrize(
    ("version_string", "output", "expected"),
    (
        (
            Version(7, 9),
            "package1.x86_64\npackage1.s390x\npackage2.x86_64\npackage2.ppc64le\n",
            ["package1.x86_64", "package1.s390x", "package2.x86_64", "package2.ppc64le"],
        ),
        (
            Version(7, 9),
            "package1.x86_64\npackage1.i686\npackage1.s390x\npackage2.x86_64\npackage2.ppc64le\n",
            ["package1.x86_64", "package1.i686", "package1.s390x", "package2.x86_64", "package2.ppc64le"],
        ),
        (
            Version(8, 8),
            "package1.x86_64\npackage1.s390x\npackage2.x86_64\npackage2.ppc64le\n",
            ["package1.x86_64", "package1.s390x", "package2.x86_64", "package2.ppc64le"],
        ),
        (
            Version(8, 8),
            "package1.x86_64\npackage1.i686\npackage1.s390x\npackage2.x86_64\npackage2.ppc64le\n",
            ["package1.x86_64", "package1.i686", "package1.s390x", "package2.x86_64", "package2.ppc64le"],
        ),
    ),
)
def test_duplicate_packages_error(
    monkeypatch, version_string, output, expected, global_tool_opts, duplicate_packages_action
):

    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_value=(output, 0)))
    monkeypatch.setattr(system_info, "version", version_string)

    monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)

    duplicate_packages_action.run()

    unit_tests.assert_actions_result(
        duplicate_packages_action,
        level="ERROR",
        id="DUPLICATE_PACKAGES_FOUND",
        title="Duplicate packages found on the system",
        description="The system contains one or more packages with multiple versions.",
        diagnosis="The following packages have multiple versions: %s." % ", ".join(expected),
        remediations="This error can be resolved by removing duplicate versions of the listed packages."
        " The command 'package-cleanup' can be used to automatically remove duplicate packages"
        " on the system.",
    )


@pytest.mark.parametrize(
    ("version_string", "output", "ret_code"),
    (
        (Version(7, 9), "Name or service not known", 0),
        (Version(8, 8), "Failed to download metadata for repo", 1),
    ),
)
def test_duplicate_packages_unsuccessful(
    monkeypatch, version_string, output, global_tool_opts, ret_code, duplicate_packages_action
):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_value=(output, ret_code)))
    monkeypatch.setattr(system_info, "version", version_string)
    monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)
    duplicate_packages_action.run()

    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="DUPLICATE_PACKAGES_FAILURE",
                title="Duplicate packages check unsuccessful",
                description="The duplicate packages check did not run successfully.",
                diagnosis="The check likely failed due to lack of access to enabled repositories on the system.",
                remediations="Ensure that you can access all repositories enabled on the system and re-run convert2rhel."
                " If the issue still persists manually check if there are any package duplicates on the system and remove them to ensure a successful conversion.",
            ),
        )
    )
    assert expected.issuperset(duplicate_packages_action.messages)
    assert expected.issubset(duplicate_packages_action.messages)


@pytest.mark.parametrize(
    ("output"),
    ((""),),
)
def test_duplicate_packages_success(monkeypatch, duplicate_packages_action, output):

    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_value=(output, 0)))
    duplicate_packages_action.run()
    unit_tests.assert_actions_result(
        duplicate_packages_action,
        level="SUCCESS",
    )
