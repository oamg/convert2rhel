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

from convert2rhel import unit_tests, utils
from convert2rhel.actions.system_checks import duplicate_packages
from convert2rhel.unit_tests import RunSubprocessMocked


@pytest.fixture
def duplicate_packages_action():
    return duplicate_packages.DuplicatePackages()


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        (
            "package1.x86_64\npackage1.s390x\npackage2.x86_64\npackage2.ppc64le\n",
            ["package1.x86_64", "package1.s390x", "package2.x86_64", "package2.ppc64le"],
        ),
        (
            "package1.x86_64\npackage1.i686\npackage1.s390x\npackage2.x86_64\npackage2.ppc64le\n",
            ["package1.x86_64", "package1.i686", "package1.s390x", "package2.x86_64", "package2.ppc64le"],
        ),
    ),
)
def test_duplicate_packages_error(monkeypatch, output, expected, duplicate_packages_action):

    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_value=(output, 0)))
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
