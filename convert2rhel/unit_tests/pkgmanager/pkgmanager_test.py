# -*- coding: utf-8 -*-
#
# Copyright(C) 2022 Red Hat, Inc.
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

from convert2rhel import pkgmanager, utils
from convert2rhel.systeminfo import Version, system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import RunSubprocessMocked, run_subprocess_side_effect
from convert2rhel.unit_tests.conftest import centos7, centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
def test_create_transaction_handler_yum(monkeypatch):
    yum_transaction_handler_mock = mock.Mock()
    monkeypatch.setattr(pkgmanager.handlers.yum, "YumTransactionHandler", yum_transaction_handler_mock)
    pkgmanager.create_transaction_handler()

    assert yum_transaction_handler_mock.called


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
def test_create_transaction_handler_dnf(monkeypatch):
    dnf_transaction_handler_mock = mock.Mock()
    monkeypatch.setattr(pkgmanager.handlers.dnf, "DnfTransactionHandler", dnf_transaction_handler_mock)
    pkgmanager.create_transaction_handler()

    assert dnf_transaction_handler_mock.called


@pytest.mark.parametrize(
    ("ret_code", "expected"),
    ((0, "Cached repositories metadata cleaned successfully."), (1, "Failed to clean yum metadata")),
)
def test_clean_yum_metadata(ret_code, expected, monkeypatch, caplog):
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (
                ("yum", "clean", "metadata", "--enablerepo=*", "--quiet"),
                (expected, ret_code),
            ),
        ),
    )
    monkeypatch.setattr(
        pkgmanager.utils,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    pkgmanager.clean_yum_metadata()

    assert expected in caplog.records[-1].message


def test_rpm_db_lock():
    pkg_obj_mock = mock.Mock()

    with pkgmanager.rpm_db_lock(pkg_obj_mock):
        pass

    assert pkg_obj_mock.rpmdb is None


class TestCallYumCmd:
    def test_call_yum_cmd(self, monkeypatch):
        monkeypatch.setattr(system_info, "version", Version(8, 0))
        monkeypatch.setattr(system_info, "releasever", "8")
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        pkgmanager.call_yum_cmd("install")

        assert utils.run_subprocess.cmd == [
            "yum",
            "install",
            "--setopt=exclude=",
            "-y",
            "--releasever=8",
            "--setopt=module_platform_id=platform:el8",
        ]

    @centos7
    def test_call_yum_cmd_not_setting_releasever(self, pretend_os, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        pkgmanager.call_yum_cmd("install", set_releasever=False)

        assert utils.run_subprocess.cmd == ["yum", "install", "--setopt=exclude=", "-y"]

    @centos7
    def test_call_yum_cmd_with_disablerepo_and_enablerepo(self, pretend_os, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        monkeypatch.setattr(tool_opts, "no_rhsm", True)
        monkeypatch.setattr(tool_opts, "disablerepo", ["*"])
        monkeypatch.setattr(tool_opts, "enablerepo", ["rhel-7-extras-rpm"])

        pkgmanager.call_yum_cmd("install")

        assert utils.run_subprocess.cmd == [
            "yum",
            "install",
            "--setopt=exclude=",
            "-y",
            "--disablerepo=*",
            "--releasever=7Server",
            "--enablerepo=rhel-7-extras-rpm",
        ]

    @centos7
    def test_call_yum_cmd_with_submgr_enabled_repos(self, pretend_os, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        monkeypatch.setattr(system_info, "submgr_enabled_repos", ["rhel-7-extras-rpm"])
        monkeypatch.setattr(tool_opts, "enablerepo", ["not-to-be-used-in-the-yum-call"])

        pkgmanager.call_yum_cmd("install")

        assert utils.run_subprocess.cmd == [
            "yum",
            "install",
            "--setopt=exclude=",
            "-y",
            "--releasever=7Server",
            "--enablerepo=rhel-7-extras-rpm",
        ]

    @centos7
    def test_call_yum_cmd_with_repo_overrides(self, pretend_os, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        monkeypatch.setattr(system_info, "submgr_enabled_repos", ["not-to-be-used-in-the-yum-call"])
        monkeypatch.setattr(tool_opts, "enablerepo", ["not-to-be-used-in-the-yum-call"])

        pkgmanager.call_yum_cmd("install", ["pkg"], enable_repos=[], disable_repos=[])

        assert utils.run_subprocess.cmd == ["yum", "install", "--setopt=exclude=", "-y", "--releasever=7Server", "pkg"]

        pkgmanager.call_yum_cmd(
            "install",
            ["pkg"],
            enable_repos=["enable-repo"],
            disable_repos=["disable-repo"],
        )

        assert utils.run_subprocess.cmd == [
            "yum",
            "install",
            "--setopt=exclude=",
            "-y",
            "--disablerepo=disable-repo",
            "--releasever=7Server",
            "--enablerepo=enable-repo",
            "pkg",
        ]

    @centos8
    def test_call_yum_cmd_nothing_to_do(self, pretend_os, monkeypatch, caplog):
        monkeypatch.setattr(
            utils, "run_subprocess", RunSubprocessMocked(return_code=1, return_string="Error: Nothing to do\n")
        )
        stdout, returncode = pkgmanager.call_yum_cmd("install", ["pkg"], enable_repos=[], disable_repos=[])

        assert returncode == 0
        assert stdout == "Error: Nothing to do\n"
        assert utils.run_subprocess.cmd == [
            "yum",
            "install",
            "--setopt=exclude=",
            "-y",
            "--releasever=8.5",
            "--setopt=module_platform_id=platform:el8",
            "pkg",
        ]
        assert "Yum has nothing to do. Ignoring" in caplog.records[-1].message

    @centos8
    def test_call_yum_cmd_custom_release_set(self, pretend_os, monkeypatch, caplog):
        monkeypatch.setattr(
            utils, "run_subprocess", RunSubprocessMocked(return_code=1, return_string="Error: Nothing to do\n")
        )
        stdout, returncode = pkgmanager.call_yum_cmd(
            "install", ["pkg"], enable_repos=[], disable_repos=[], custom_releasever="8"
        )

        assert returncode == 0
        assert stdout == "Error: Nothing to do\n"
        assert utils.run_subprocess.cmd == [
            "yum",
            "install",
            "--setopt=exclude=",
            "-y",
            "--releasever=8",
            "--setopt=module_platform_id=platform:el8",
            "pkg",
        ]
        assert "Yum has nothing to do. Ignoring" in caplog.records[-1].message

    @centos8
    def test_call_yum_cmd_assertion_error(self, pretend_os, monkeypatch, global_system_info):
        monkeypatch.setattr(pkgmanager, "system_info", global_system_info)
        global_system_info.releasever = None
        monkeypatch.setattr(
            utils, "run_subprocess", RunSubprocessMocked(return_code=1, return_string="Error: Nothing to do\n")
        )

        with pytest.raises(AssertionError, match="custom_releasever or system_info.releasever must be set."):
            pkgmanager.call_yum_cmd("install", ["pkg"], enable_repos=[], disable_repos=[], custom_releasever=None)

    @pytest.mark.parametrize(
        ("setopts",),
        (
            (["obsoletes=0"],),
            (["varsdir=test"],),
            (["reposdir=test"],),
            (["reposdir=test", "obsoletes=1"],),
        ),
    )
    @centos8
    def test_call_yum_cmd_setopts_override(self, setopts, pretend_os, monkeypatch, caplog):
        monkeypatch.setattr(
            utils, "run_subprocess", RunSubprocessMocked(return_code=1, return_string="Error: Nothing to do\n")
        )
        stdout, returncode = pkgmanager.call_yum_cmd("install", ["pkg"], set_releasever=False, setopts=setopts)

        assert returncode == 0
        assert stdout == "Error: Nothing to do\n"
        expected_cmd = [
            "yum",
            "install",
            "--setopt=exclude=",
            "-y",
            "--setopt=module_platform_id=platform:el8",
        ]

        for setopt in setopts:
            expected_cmd.append("--setopt=%s" % setopt)

        expected_cmd.append("pkg")
        assert utils.run_subprocess.cmd == expected_cmd
        assert "Yum has nothing to do. Ignoring" in caplog.records[-1].message
