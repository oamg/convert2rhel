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

import pytest
import six

from convert2rhel import actions, logger, systeminfo, utils
from convert2rhel.actions.post_conversion import modified_rpm_files_diff
from convert2rhel.systeminfo import system_info


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def modified_rpm_files_diff_instance():
    return modified_rpm_files_diff.ModifiedRPMFilesDiff()


def test_modified_rpm_files_diff_with_no_rpm_va(
    monkeypatch, modified_rpm_files_diff_instance, caplog, global_tool_opts
):
    global_tool_opts.no_rpm_va = True
    monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)

    # This can be removed when systeminfo is ported to use global logger
    monkeypatch.setattr(systeminfo.system_info, "logger", logging.getLogger(__name__))

    modified_rpm_files_diff_instance.run()

    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="SKIPPED_MODIFIED_RPM_FILES_DIFF",
                title="Skipped comparison of 'rpm -Va' output from before and after the conversion",
                description="Comparison of 'rpm -Va' output was not performed due to missing output "
                "of the 'rpm -Va' run before the conversion.",
                diagnosis="This is caused mainly by using '--no-rpm-va' argument for convert2rhel.",
            ),
        ),
    )

    assert expected.issubset(modified_rpm_files_diff_instance.messages)
    assert expected.issuperset(modified_rpm_files_diff_instance.messages)
    assert "Skipping comparison of the 'rpm -Va' output from before and after the conversion." in caplog.messages


@pytest.mark.parametrize(
    ("rpm_va_pre_output", "rpm_va_post_output", "expected_raw", "different"),
    (
        (
            """S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo
            S.5.?..T.        /etc/yum.repos.d/CentOS-Linux-BaseOS.repo""",
            """S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo
            S.5.?..T.        /etc/yum.repos.d/CentOS-Linux-BaseOS.repo""",
            [],
            False,
        ),
        (
            """S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo""",
            """S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo
            S.5.?..T.        /etc/yum.repos.d/CentOS-Linux-BaseOS.repo""",
            actions.ActionMessage(
                level="INFO",
                id="FOUND_MODIFIED_RPM_FILES",
                title="Modified rpm files from before and after the conversion were found",
                description="Comparison of modified rpm files from before and after the conversion: \n"
                "--- {path}/rpm_va.log\n"
                "+++ {path}/rpm_va_after_conversion.log\n"
                "@@ -1,0 +2 @@\n"
                "+S.5.?..T.        /etc/yum.repos.d/CentOS-Linux-BaseOS.repo",
            ),
            True,
        ),
    ),
)
def test_modified_rpm_files_diff_without_differences_after_conversion(
    monkeypatch,
    modified_rpm_files_diff_instance,
    caplog,
    tmpdir,
    rpm_va_pre_output,
    rpm_va_post_output,
    different,
    expected_raw,
    global_tool_opts,
):
    monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)
    monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=(rpm_va_pre_output, 0)))
    monkeypatch.setattr(logger, "LOG_DIR", str(tmpdir))
    # Need to patch explicitly since the modified_rpm_files_diff is already instanciated in the fixture
    monkeypatch.setattr(modified_rpm_files_diff, "LOG_DIR", str(tmpdir))

    # This can be removed when systeminfo is ported to use global logger
    monkeypatch.setattr(systeminfo.system_info, "logger", logging.getLogger(__name__))

    # Generate the pre-conversion rpm -Va output
    system_info.generate_rpm_va()

    # Change the output to the post conversion output
    monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=(rpm_va_post_output, 0)))

    modified_rpm_files_diff_instance.run()

    if different:
        # Add the test paths to the right places of diff
        expected_raw.description = expected_raw.description.format(path=str(tmpdir))
        expected = {expected_raw}

    assert ("Comparison of modified rpm files from before and after the conversion:" in caplog.text) == different

    if different:
        assert expected.issubset(modified_rpm_files_diff_instance.messages)
        assert expected.issuperset(modified_rpm_files_diff_instance.messages)
    else:
        assert modified_rpm_files_diff_instance.messages == []
