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

import logging
import os

import pytest
import six

from convert2rhel import actions, logger, systeminfo, toolopts, unit_tests, utils
from convert2rhel.actions.post_conversion import modified_rpm_files_diff
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel.unit_tests.conftest import centos8


@pytest.fixture
def modified_rpm_files_diff_instance():
    return modified_rpm_files_diff.ModifiedRPMFilesDiff()


def test_modified_rpm_files_diff_with_no_rpm_va(monkeypatch, modified_rpm_files_diff_instance, caplog):
    monkeypatch.setattr(toolopts.tool_opts, "no_rpm_va", mock.Mock(return_value=True))

    # This can be removed when systeminfo is ported to use global logger
    monkeypatch.setattr(systeminfo.system_info, "logger", logging.getLogger(__name__))

    modified_rpm_files_diff_instance.run()

    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="SKIPPED_MODIFIED_RPM_FILES_DIFF",
                title="Skipped comparison of 'rmp -Va' output from before and after the conversion.",
                description="Comparison of 'rpm -Va' output was skipped due missing output "
                "of the 'rpm -Va' run before the conversion.",
                diagnosis="This is caused mainly by using '--no-rpm-va' argument for convert2rhel.",
            ),
        )
    )

    assert expected.issuperset(modified_rpm_files_diff_instance.messages)
    assert "Skipping comparison of the 'rpm -Va' output from before and after the conversion." in caplog.messages


@pytest.mark.parametrize(
    ("rpm_va_output", "difference"),
    (
        (
            [
                """S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo
                S.5.?..T.        /etc/yum.repos.d/CentOS-Linux-AppStream.repo""",
                """S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo
                S.5.?..T.        /etc/yum.repos.d/CentOS-Linux-AppStream.repo""",
            ],
            False,
        ),
        (
            [
                """S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo""",
                """S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo
                S.5.?..T.        /etc/yum.repos.d/CentOS-Linux-AppStream.repo""",
            ],
            True,
        ),
    ),
)
def test_modified_rpm_files_diff_without_differences_after_conversion(
    monkeypatch, modified_rpm_files_diff_instance, caplog, tmpdir, rpm_va_output, difference
):
    monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=rpm_va_output))
    monkeypatch.setattr(logger, "LOG_DIR", str(tmpdir))
    monkeypatch.setattr(modified_rpm_files_diff, "LOG_DIR", str(tmpdir))

    # This can be removed when systeminfo is ported to use global logger
    monkeypatch.setattr(systeminfo.system_info, "logger", logging.getLogger(__name__))

    # Generate the pre-conversion rpm -Va output
    system_info.generate_rpm_va()

    modified_rpm_files_diff_instance.run()

    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="FOUND_MODIFIED_RPM_FILES",
                title="Modified rpm files from before and after the conversion were found.",
                description="Comparison of modified rpm files from before and after " "the conversion: \n",
            ),
        )
    )

    # TODO fix the asserts
    # TODO for some reason the loaded post_rpm_va is the same as the pre. Fix this
    assert ("Comparison of modified rpm files from before and after the conversion:" in caplog.messages) == difference
    assert expected.issubset(modified_rpm_files_diff_instance.messages) == difference


def test_modified_rpm_files_diff_with_differences_after_conversion(self, monkeypatch, caplog):
    monkeypatch.setattr(system_info, "generate_rpm_va", mock.Mock())
    monkeypatch.setattr(os.path, "exists", mock.Mock(return_value=True))
    monkeypatch.setattr(tool_opts, "no_rpm_va", False)
    monkeypatch.setattr(
        utils,
        "get_file_content",
        mock.Mock(
            side_effect=(
                [".M.......  g /etc/pki/ca-trust/extracted/java/cacerts"],
                [
                    ".M.......  g /etc/pki/ca-trust/extracted/java/cacerts",
                    "S.5....T.  c /etc/yum.conf",
                ],
            )
        ),
    )

    system_info.modified_rpm_files_diff()

    assert any("S.5....T.  c /etc/yum.conf" in elem.message for elem in caplog.records if elem.levelname == "INFO")
