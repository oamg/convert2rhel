# -*- coding: utf-8 -*-
#
# Copyright(C) 2018 Red Hat, Inc.
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
import getpass
import logging
import os
import sys
import unittest

import pytest
import six

from convert2rhel.utils import prompt_user


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from collections import namedtuple

from six.moves import mock

from convert2rhel import unit_tests, utils  # Imports unit_tests/__init__.py
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests import is_rpm_based_os


class TestUtils(unittest.TestCase):
    class DummyFuncMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0

        def __call__(self, *args, **kargs):
            self.called += 1

    class RunSubprocessMocked(unit_tests.MockFunction):
        def __init__(self, output="Test output", ret_code=0):
            self.cmd = []
            self.cmds = []
            self.called = 0
            self.output = output
            self.ret_code = ret_code

        def __call__(self, cmd, print_cmd=True, print_output=True):
            self.cmd = cmd
            self.cmds.append(cmd)
            self.called += 1
            return self.output, self.ret_code

    class DummyGetUID(unit_tests.MockFunction):
        def __init__(self, uid):
            self.uid = uid

        def __call__(self, *args, **kargs):
            return self.uid

    @unit_tests.mock(os, "geteuid", DummyGetUID(1000))
    def test_require_root_is_not_root(self):
        self.assertRaises(SystemExit, utils.require_root)

    @unit_tests.mock(os, "geteuid", DummyGetUID(0))
    def test_require_root_is_root(self):
        self.assertEqual(utils.require_root(), None)

    def test_run_subprocess(self):
        output, code = utils.run_subprocess(["echo", "foobar"])

        self.assertEqual(output, "foobar\n")
        self.assertEqual(code, 0)

        output, code = utils.run_subprocess(["sh", "-c", "exit 56"])  # a command that just returns 56

        self.assertEqual(output, "")
        self.assertEqual(code, 56)

    DOWNLOADED_RPM_NVRA = "kernel-4.18.0-193.28.1.el8_2.x86_64"
    DOWNLOADED_RPM_NEVRA = "7:%s" % DOWNLOADED_RPM_NVRA
    DOWNLOADED_RPM_FILENAME = "%s.rpm" % DOWNLOADED_RPM_NVRA

    YUMDOWNLOADER_OUTPUTS = [
        "Last metadata expiration check: 2:47:36 ago on Thu 22 Oct 2020 06:07:08 PM CEST.\n"
        "%s         2.7 MB/s | 2.8 MB     00:01" % DOWNLOADED_RPM_FILENAME,
        "/var/lib/convert2rhel/%s already exists and appears to be complete" % DOWNLOADED_RPM_FILENAME,
        "using local copy of %s" % DOWNLOADED_RPM_NEVRA,
        "[SKIPPED] %s: Already downloaded" % DOWNLOADED_RPM_FILENAME,
    ]

    @unit_tests.mock(
        utils,
        "download_pkg",
        lambda pkg, dest, reposdir, enable_repos, disable_repos, set_releasever: "/filepath/",
    )
    def test_download_pkgs(self):
        paths = utils.download_pkgs(
            ["pkg1", "pkg2"],
            "/dest/",
            "/reposdir/",
            ["repo1"],
            ["repo2"],
            False,
        )

        self.assertEqual(paths, ["/filepath/", "/filepath/"])

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(8, 0))
    @unit_tests.mock(system_info, "releasever", "8")
    @unit_tests.mock(utils, "run_cmd_in_pty", RunSubprocessMocked(ret_code=0))
    @unit_tests.mock(
        utils,
        "get_rpm_path_from_yumdownloader_output",
        lambda x, y, z: "/path/test.rpm",
    )
    def test_download_pkg_success_with_all_params(self):
        dest = "/test dir/"
        reposdir = "/my repofiles/"
        enable_repos = ["repo1", "repo2"]
        disable_repos = ["*"]

        path = utils.download_pkg(
            "kernel",
            dest=dest,
            reposdir=reposdir,
            enable_repos=enable_repos,
            disable_repos=disable_repos,
            set_releasever=True,
        )

        self.assertEqual(
            [
                "yumdownloader",
                "-v",
                "--destdir=%s" % dest,
                "--setopt=reposdir=%s" % reposdir,
                "--disablerepo=*",
                "--enablerepo=repo1",
                "--enablerepo=repo2",
                "--releasever=8",
                "--setopt=module_platform_id=platform:el8",
                "kernel",
            ],
            utils.run_cmd_in_pty.cmd,
        )
        self.assertTrue(path)  # path is not None (which is the case of unsuccessful download)

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(utils, "run_cmd_in_pty", RunSubprocessMocked(ret_code=1))
    @unit_tests.mock(os, "environ", {"CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK": "1"})
    def test_download_pkg_failed_download_overridden(self):
        path = utils.download_pkg("kernel")

        self.assertEqual(path, None)

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(utils, "run_cmd_in_pty", RunSubprocessMocked(ret_code=1))
    @unit_tests.mock(os, "environ", {})
    def test_download_pkg_failed_download_exit(self):
        self.assertRaises(SystemExit, utils.download_pkg, "kernel")

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(utils, "run_cmd_in_pty", RunSubprocessMocked(ret_code=0))
    def test_download_pkg_incorrect_output(self):
        utils.run_cmd_in_pty.output = "bogus"

        path = utils.download_pkg("kernel")

        self.assertEqual(path, None)

        utils.run_cmd_in_pty.output = ""

        path = utils.download_pkg("kernel")

        self.assertEqual(path, None)

    def test_get_rpm_path_from_yumdownloader_output(self):
        for output in self.YUMDOWNLOADER_OUTPUTS:
            utils.run_cmd_in_pty.output = output

            path = utils.get_rpm_path_from_yumdownloader_output("cmd not important", output, utils.TMP_DIR)

            self.assertEqual(path, os.path.join(utils.TMP_DIR, self.DOWNLOADED_RPM_FILENAME))

    def test_is_rpm_based_os(self):
        assert is_rpm_based_os() in (True, False)


@pytest.mark.parametrize(
    "command, expected_output, expected_code",
    (
        (["echo", "foobar"], "foobar", 0),
        (["sh", "-c", "exit 56"], "", 56),
    ),
)
def test_run_cmd_in_pty_simple(command, expected_output, expected_code, monkeypatch):
    output, code = utils.run_cmd_in_pty(command)
    assert output.strip() == expected_output
    assert code == expected_code


def test_run_cmd_in_pty_expect_script():
    if sys.version_info < (3,):
        prompt_cmd = "raw_input"
    else:
        prompt_cmd = "input"
    output, code = utils.run_cmd_in_pty(
        [sys.executable, "-c", 'print(%s("Ask for password: "))' % prompt_cmd],
        expect_script=(("password: *", "Foo bar\n"),),
    )

    assert output.strip().splitlines()[-1] == "Foo bar"
    assert code == 0


@pytest.mark.parametrize(
    "print_cmd, print_output",
    (
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ),
)
def test_run_cmd_in_pty_quiet_options(print_cmd, print_output, global_tool_opts, caplog):
    global_tool_opts.debug = True
    caplog.set_level(logging.DEBUG)

    output, code = utils.run_cmd_in_pty(["echo", "foo bar"], print_cmd=print_cmd, print_output=print_output)

    expected_count = 1  # There will always be one debug log stating the pty columns
    if print_cmd:
        assert caplog.records[0].levelname == "DEBUG"
        assert caplog.records[0].message.strip() == "Calling command 'echo foo bar'"
        expected_count += 1

    if print_output:
        assert caplog.records[-1].levelname == "INFO"
        assert caplog.records[-1].message.strip() == "foo bar"
        expected_count += 1

    assert len(caplog.records) == expected_count


def test_run_cmd_in_pty_check_for_deprecated_string():
    with pytest.raises(TypeError, match="cmd should be a list, not a str"):
        utils.run_cmd_in_pty("echo foobar")


TERMINAL_SIZE_SCRIPT = """
def terminal_size():
    import fcntl, termios, struct, sys
    h, w, hp, wp = struct.unpack('HHHH',
        fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ,
        struct.pack('HHHH', 0, 0, 0, 0)))
    return w, h

print(terminal_size()[0])
"""


@pytest.mark.parametrize(
    ("columns",),
    (
        (40,),
        (120,),
    ),
)
def test_run_cmd_in_pty_size_set_on_startup(columns, tmpdir):
    """Test whether run_cmd_in_pty sets the terminal window size on startup."""
    with open(str(tmpdir / "terminal-test.py"), "w") as f:
        f.write(TERMINAL_SIZE_SCRIPT)

    output, return_code = utils.run_cmd_in_pty([sys.executable, str(tmpdir / "terminal-test.py")], columns=columns)

    assert int(output.strip()) == columns


def test_run_cmd_in_pty_size_set_on_startup_unknown_typeerror():
    """Test whether we re-raise TypeError when we don't know how to handle it."""
    # Our compat class handles TypeError caused by passing dimensions.  Check
    # that TypeError caused by something else re-raises the TypeError.
    with pytest.raises(TypeError, match=".*got an unexpected keyword argument 'unknown'"):
        _dummy = utils.PexpectSpawnWithDimensions("/bin/true", [], unknown=False)


def test_get_package_name_from_rpm(monkeypatch):
    monkeypatch.setattr(utils, "rpm", get_rpm_mocked())
    monkeypatch.setattr(utils, "get_rpm_header", lambda _: get_rpm_header_mocked())
    assert utils.get_package_name_from_rpm("/path/to.rpm") == "pkg1"


class TransactionSetMocked(unit_tests.MockFunction):
    def __call__(self):
        return self

    def setVSFlags(self, flags):
        return

    def hdrFromFdno(self, rpmfile):
        return get_rpm_header_mocked()


class ObjectFromDictSpec(dict):
    def __getattr__(self, item):
        return self.__getitem__(item)


def get_rpm_mocked():
    return ObjectFromDictSpec(
        {
            "RPMTAG_NAME": "RPMTAG_NAME",
            "RPMTAG_VERSION": "RPMTAG_VERSION",
            "RPMTAG_RELEASE": "RPMTAG_RELEASE",
            "RPMTAG_EVR": "RPMTAG_EVR",
            "TransactionSet": TransactionSetMocked,
            "_RPMVSF_NOSIGNATURES": mock.Mock(),
        }
    )


def get_rpm_header_mocked():
    rpm = get_rpm_mocked()
    return {
        rpm.RPMTAG_NAME: "pkg1",
        rpm.RPMTAG_VERSION: "1",
        rpm.RPMTAG_RELEASE: "2",
        rpm.RPMTAG_EVR: "1-2",
    }


def test_get_rpm_header(monkeypatch):
    rpm = get_rpm_mocked()
    monkeypatch.setattr(utils, "rpm", rpm)
    assert utils.get_rpm_header("/path/to.rpm", _open=mock.mock_open())[rpm.RPMTAG_NAME] == "pkg1"


@pytest.mark.parametrize("dir_name", ("/existing", "/nonexisting", None))
# TODO change to tmpdir fixture
def test_remove_tmp_dir(monkeypatch, dir_name, caplog, tmpdir):
    if dir_name == "/existing":
        path = str(tmpdir.mkdir(dir_name))
    else:
        path = dir_name
    monkeypatch.setattr(utils, "TMP_DIR", value=path)

    utils.remove_tmp_dir()

    if dir_name == "/existing":
        assert "Temporary folder " + str(path) + " removed" in caplog.text
    elif dir_name == "/nonexisting":
        assert "Failed removing temporary folder " + dir_name in caplog.text
    else:
        assert "TypeError error while removing temporary folder " in caplog.text


@pytest.mark.parametrize(
    ("question", "is_password", "response"),
    (
        ("Username: ", False, "test"),
        ("Password: ", True, "test"),
    ),
)
def test_prompt_user(question, is_password, response, monkeypatch):
    if is_password:
        monkeypatch.setattr(getpass, "getpass", lambda _: response)
    else:
        monkeypatch.setattr(six.moves, "input", lambda _: response)

    assert prompt_user(question, is_password) == response


@pytest.mark.parametrize(
    ("string_version", "nevra"),
    (
        ("5.14.15-300.fc35", ("0", "5.14.15", "300.fc35")),
        ("0.17-9.fc35", ("0", "0.17", "9.fc35")),
        ("2.34.1-2.fc35", ("0", "2.34.1", "2.fc35")),
        (
            "0.9.1-2.20210420git36391559.fc35",
            ("0", "0.9.1", "2.20210420git36391559.fc35"),
        ),
        ("2:8.2.3568-1.fc35", ("2", "8.2.3568", "1.fc35")),
        (
            "4.6~pre16262021g84ef6bd9-3.fc35",
            ("0", "4.6~pre16262021g84ef6bd9", "3.fc35"),
        ),
    ),
)
def test_string_to_version(string_version, nevra):
    nevra_version = utils.string_to_version(string_version)
    assert nevra_version == nevra


@pytest.mark.parametrize(
    ("path_exists", "list_dir", "expected"),
    (
        (True, ["dir-1", "dir-2"], 0),
        (True, [], 2),
        (False, [], 0),
        (False, ["dir-1", "dir-2"], 0),
    ),
)
def test_remove_orphan_folders(path_exists, list_dir, expected, tmpdir, monkeypatch):
    os_remove_mock = mock.Mock()
    monkeypatch.setattr(os.path, "exists", value=lambda path: path_exists)
    monkeypatch.setattr(os, "listdir", value=lambda path: list_dir)
    monkeypatch.setattr(os, "rmdir", value=os_remove_mock)

    utils.remove_orphan_folders()
    assert os_remove_mock.call_count == expected
