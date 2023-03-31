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
import json
import logging
import os
import shutil
import sys
import unittest

import pexpect
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
        lambda pkg, dest, reposdir, enable_repos, disable_repos, set_releasever, custom_releasever, varsdir: "/filepath/",
    )
    def test_download_pkgs(self):
        paths = utils.download_pkgs(
            pkgs=["pkg1", "pkg2"],
            dest="/dest/",
            reposdir="/reposdir/",
            enable_repos=["repo1"],
            disable_repos=["repo2"],
            set_releasever=False,
            custom_releasever=8,
            varsdir="/tmp",
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
            pkg="kernel",
            dest=dest,
            reposdir=reposdir,
            enable_repos=enable_repos,
            disable_repos=disable_repos,
            set_releasever=True,
            custom_releasever="8",
            varsdir="/tmp",
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
                "--setopt=varsdir=/tmp",
                "--setopt=module_platform_id=platform:el8",
                "kernel",
            ],
            utils.run_cmd_in_pty.cmd,
        )
        self.assertTrue(path)  # path is not None (which is the case of unsuccessful download)

    @unit_tests.mock(system_info, "releasever", None)
    def test_download_pkg_assertion_error(self):
        with pytest.raises(AssertionError, match="custom_releasever or system_info.releasever must be set."):
            utils.download_pkg(
                pkg="kernel",
                set_releasever=True,
                custom_releasever=None,
            )

    @unit_tests.mock(system_info, "releasever", "7Server")
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(utils, "run_cmd_in_pty", RunSubprocessMocked(ret_code=1))
    @unit_tests.mock(os, "environ", {"CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK": "1"})
    def test_download_pkg_failed_download_overridden(self):
        path = utils.download_pkg("kernel")

        self.assertEqual(path, None)

    @unit_tests.mock(system_info, "releasever", "7Server")
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(utils, "run_cmd_in_pty", RunSubprocessMocked(ret_code=1))
    @unit_tests.mock(os, "environ", {})
    def test_download_pkg_failed_download_exit(self):
        self.assertRaises(SystemExit, utils.download_pkg, "kernel")

    @unit_tests.mock(system_info, "releasever", "7Server")
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
def test_run_cmd_in_pty_simple(command, expected_output, expected_code, capfd, monkeypatch):
    with capfd.disabled():
        output, code = utils.run_cmd_in_pty(command)
    assert output.strip() == expected_output
    assert code == expected_code


def test_run_cmd_in_pty_expect_script(capfd):
    if sys.version_info < (3,):
        prompt_cmd = "raw_input"
    else:
        prompt_cmd = "input"
    with capfd.disabled():
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
def test_run_cmd_in_pty_quiet_options(print_cmd, print_output, global_tool_opts, caplog, capfd):
    global_tool_opts.debug = True
    caplog.set_level(logging.DEBUG)

    with capfd.disabled():
        utils.run_cmd_in_pty(["echo", "foo bar"], print_cmd=print_cmd, print_output=print_output)

    expected_count = 0
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
def test_run_cmd_in_pty_size_set(columns, capfd, tmpdir):
    """Test whether run_cmd_in_pty sets the terminal window size on startup."""
    with open(str(tmpdir / "terminal-test.py"), "w") as f:
        f.write(TERMINAL_SIZE_SCRIPT)

    # Need to disable capfd because pytest capturing interferes with pexpect-2.3's ability to set
    # the pty size before starting the program.
    with capfd.disabled():
        output, _ = utils.run_cmd_in_pty([sys.executable, str(tmpdir / "terminal-test.py")], columns=columns)

    assert int(output.strip()) == columns


@pytest.mark.parametrize(
    ("columns",),
    (
        (40,),
        (120,),
    ),
)
def test_pexpectspawnwithdimensions_size_set_on_startup(columns, capfd, tmpdir):
    """Test whether run_cmd_in_pty sets the terminal window size on startup."""
    with open(str(tmpdir / "terminal-test.py"), "w") as f:
        f.write(TERMINAL_SIZE_SCRIPT)

    # Need to disable capfd because pytest capturing interferes with pexpect-2.3's ability to set
    # the pty size before starting the program.
    with capfd.disabled():
        process = utils.PexpectSpawnWithDimensions(
            sys.executable, [str(tmpdir / "terminal-test.py")], dimensions=(1, columns)
        )

    process.expect(pexpect.EOF)
    try:
        process.wait()
    except pexpect.ExceptionPexpect:
        # RHEL 7's pexpect throws an exception if the process has already exited
        # We're just waiting to be sure that the process has finished so we can
        # ignore the exception.
        pass

    # Per the pexpect API, this is necessary in order to get the return code
    process.close()

    output = process.before.decode().splitlines()[-1]

    assert int(output.strip()) == columns


def test_pexpectspawnwithdimensions_unknown_typeerror():
    """Test whether we re-raise TypeError when we don't know how to handle it."""
    # Our compat class handles TypeError caused by passing dimensions.  Check
    # that TypeError caused by something else re-raises the TypeError.
    with pytest.raises(TypeError, match=".*got an unexpected keyword argument 'unknown'"):
        utils.PexpectSpawnWithDimensions("/bin/true", [], unknown=False)


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


class TestFindKeys:
    class MockedRmtree(object):
        def __init__(self, exception, real_rmtree):
            self.called = 0
            self.exception = exception
            self.real_rmtree = real_rmtree

        def __call__(self, *args, **kwargs):
            # Fail on the first call
            self.called += 1
            if self.called == 1:
                raise self.exception

            return self.real_rmtree(*args, **kwargs)

    gpg_key = os.path.realpath(
        os.path.join(os.path.dirname(__file__), "../data/version-independent/gpg-keys/RPM-GPG-KEY-redhat-release")
    )

    def test_find_keyid(self):
        assert utils.find_keyid(self.gpg_key) == "fd431d51"

    def test_find_keyid_race_in_gpg_cleanup(self, monkeypatch):
        real_rmtree = shutil.rmtree
        monkeypatch.setattr(shutil, "rmtree", self.MockedRmtree(OSError(2, "File not found"), real_rmtree))

        assert utils.find_keyid(self.gpg_key) == "fd431d51"

    def test_find_keyid_bad_file(self, tmpdir):
        gpg_key = os.path.join(str(tmpdir), "badkeyfile")
        with open(gpg_key, "w") as f:
            f.write("bad data\n")

        with pytest.raises(
            utils.ImportGPGKeyError, match="Failed to import the rpm gpg key into a temporary keyring.*"
        ):
            utils.find_keyid(gpg_key)

    def test_find_keyid_gpg_bad_keyring(self, monkeypatch):
        class MockedRunSubProcess(object):
            def __init__(self):
                self.called = 0

            def __call__(self, *args, **kwargs):
                # Fail on the second call
                self.called += 1
                if self.called == 2:
                    return ("", 1)

                return real_run_subprocess(*args, **kwargs)

        real_run_subprocess = utils.run_subprocess
        monkeypatch.setattr(utils, "run_subprocess", MockedRunSubProcess())

        with pytest.raises(
            utils.ImportGPGKeyError, match="Failed to read the temporary keyring with the rpm gpg key:.*"
        ):
            utils.find_keyid(self.gpg_key)

    def test_find_keyid_gpg_bad_keyring_and_race_deleting_tmp_dir(self, monkeypatch):
        class MockedRunSubProcess(object):
            def __init__(self):
                self.called = 0

            def __call__(self, *args, **kwargs):
                # Fail on the second call
                self.called += 1
                if self.called == 2:
                    return ("", 1)

                return real_run_subprocess(*args, **kwargs)

        real_run_subprocess = utils.run_subprocess
        monkeypatch.setattr(utils, "run_subprocess", MockedRunSubProcess())

        real_rmtree = shutil.rmtree
        monkeypatch.setattr(shutil, "rmtree", self.MockedRmtree(OSError(2, "File not found"), real_rmtree))

        with pytest.raises(
            utils.ImportGPGKeyError, match="Failed to read the temporary keyring with the rpm gpg key:.*"
        ):
            utils.find_keyid(self.gpg_key)

    def test_find_keyid_no_gpg_output(self, monkeypatch):
        class MockedRunSubProcess(object):
            def __init__(self):
                self.called = 0

            def __call__(self, *args, **kwargs):
                # Fail on the second call
                self.called += 1
                if self.called == 2:
                    return ("", 0)

                return real_run_subprocess(*args, **kwargs)

        real_run_subprocess = utils.run_subprocess
        monkeypatch.setattr(utils, "run_subprocess", MockedRunSubProcess())

        with pytest.raises(
            utils.ImportGPGKeyError, match="Unable to determine the gpg keyid for the rpm key file: %s" % self.gpg_key
        ):
            utils.find_keyid(self.gpg_key)

    @pytest.mark.parametrize(
        ("exception", "exception_msg"),
        (
            (OSError(13, "Permission denied"), "Errno 13.*Permission denied"),
            (Exception("Unanticipated problem"), "Unanticipated problem"),
        ),
    )
    def test_find_keyid_problem_removing_directory(self, exception, exception_msg, monkeypatch):
        real_rmtree = shutil.rmtree
        monkeypatch.setattr(shutil, "rmtree", self.MockedRmtree(exception, real_rmtree))

        with pytest.raises(exception.__class__, match=exception_msg):
            utils.find_keyid(self.gpg_key)


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


@pytest.mark.parametrize(
    ("arguments", "secret_options", "expected"),
    (
        # No sanitization is being used here
        (["-h"], frozenset(), ["-h"]),
        # Random parameter
        (["--password=123", "--another"], frozenset(("--password",)), ["--password=*****", "--another"]),
        (["-p", "123", "--another"], frozenset(("-p",)), ["-p", "*****", "--another"]),
        (["-k", "123", "--another"], frozenset(("-k",)), ["-k", "*****", "--another"]),
        (
            ["--argument", "with space in it", "--another"],
            frozenset(),
            ["--argument", "with space in it", "--another"],
        ),
        (
            ["--argument=with space in it", "--another"],
            frozenset(),
            ["--argument=with space in it", "--another"],
        ),
        # Single option being passed
        (
            ["--activationkey=123"],
            frozenset(("--activationkey",)),
            ["--activationkey=*****"],
        ),
        # Hide the secrets in the short form of the options
        (
            ["-u=test", "-p=Super@Secret@Password", "-k=123", "-o=1234"],
            frozenset(
                (
                    "-u",
                    "-p",
                    "-k",
                    "-o",
                )
            ),
            ["-u=*****", "-p=*****", "-k=*****", "-o=*****"],
        ),
        # Multiple sanitizations should occur in the next test
        (
            ["--username=test", "--password=Super@Secret@Password", "--activationkey=123", "--org=1234", "-y"],
            frozenset(("--username", "--password", "--activationkey", "--org")),
            ["--username=*****", "--password=*****", "--activationkey=*****", "--org=*****", "-y"],
        ),
        # Test the same sanitization but without the equal sign ("=") in the arguments
        (
            [
                "--username",
                "test",
                "--password",
                "Super@Secret@Password",
                "--activationkey",
                "123",
                "--org",
                "1234",
                "-y",
            ],
            frozenset(("--username", "--password", "--activationkey", "--org")),
            ["--username", "*****", "--password", "*****", "--activationkey", "*****", "--org", "*****", "-y"],
        ),
        # A real world example of how the tool would be used
        (
            [
                "/usr/bin/convert2rhel",
                "--username=test",
                "--password=Super@Secret@Password",
                "--pool=e6e3f4ca-342f-11ed-b5eb-6c9466263bdf",
                "--no-rpm-va",
                "--debug",
                "-y",
            ],
            frozenset(
                (
                    "--username",
                    "--password",
                    "--activationkey",
                )
            ),
            [
                "/usr/bin/convert2rhel",
                "--username=*****",
                "--password=*****",
                "--pool=e6e3f4ca-342f-11ed-b5eb-6c9466263bdf",
                "--no-rpm-va",
                "--debug",
                "-y",
            ],
        ),
        # Test replacement of parameters with special characters
        (
            ["--password", " "],
            frozenset(
                "--password",
            ),
            ["--password", " "],
        ),
        (
            ["--password", ""],
            frozenset(
                "--password",
            ),
            ["--password", ""],
        ),
        (
            ["--password", "\\)(*&^%f %##@^%&*&^(", "--activationkey", "\\)(*&^%f %##@^%&*&^("],
            frozenset(("--password", "--activationkey")),
            ["--password", "*****", "--activationkey", "*****"],
        ),
        (
            ["-p", "\\)(*&^%f %##@^%&*&^(", "-k", "\\)(*&^%f %##@^%&*&^("],
            frozenset(("-p", "-k")),
            ["-p", "*****", "-k", "*****"],
        ),
    ),
)
def test_hide_secrets(arguments, secret_options, expected):
    sanitazed_cmd = utils.hide_secrets(arguments, secret_options=secret_options)
    assert sanitazed_cmd == expected


def test_hide_secrets_default():
    """Test that the default secret_options cover all known secrets."""
    test_cmd = [
        "register",
        "--force",
        "--username=jdoe",
        "--password=Super@Secret@Password",
        "-p=Super@Secret@Password",
        "--activationkey=123",
        "-k=123",
        "--pool=e6e3f4ca-342f-11ed-b5eb-6c9466263bdf",
        "--no-rpm-va",
        "--debug",
        "--org=0123",
    ]
    sanitized_cmd = utils.hide_secrets(test_cmd)
    assert sanitized_cmd == [
        "register",
        "--force",
        "--username=*****",
        "--password=*****",
        "-p=*****",
        "--activationkey=*****",
        "-k=*****",
        "--pool=e6e3f4ca-342f-11ed-b5eb-6c9466263bdf",
        "--no-rpm-va",
        "--debug",
        "--org=*****",
    ]


def test_hide_secrets_no_secrets():
    """Test that a list with no secrets to hide is not modified."""
    test_cmd = [
        "register",
        "--force",
        "--no-rpm-va",
        "-y",
    ]
    sanitized_cmd = utils.hide_secrets(test_cmd)
    assert sanitized_cmd == [
        "register",
        "--force",
        "--no-rpm-va",
        "-y",
    ]


def test_hide_secret_unexpected_input(caplog):
    test_cmd = [
        "register",
        "--force",
        "--password=SECRETS",
        "--username=jdoe",
        "--org=0123",
        "--activationkey",
        # This is missing the activationkey as the second argument
    ]

    sanitized_cmd = utils.hide_secrets(test_cmd)

    assert sanitized_cmd == [
        "register",
        "--force",
        "--password=*****",
        "--username=*****",
        "--org=*****",
        "--activationkey",
    ]
    assert len(caplog.records) == 1
    assert caplog.records[-1].levelname == "DEBUG"
    assert "Passed arguments had an option, '--activationkey', without an expected secret parameter" in caplog.text


@pytest.mark.parametrize(
    ("items", "expected"),
    (
        ([], ""),
        (["zebra"], "zebra"),
        (["zebra", "ostrich"], "zebra and ostrich"),
        (["zebra", "ostrich", "whale"], "zebra, ostrich, and whale"),
        (["a", "b", "c"], "a, b, and c"),
        ("abcdefg", "a, b, c, d, e, f, and g"),
    ),
)
def test_format_sequence_as_message(items, expected):
    assert utils.format_sequence_as_message(items) == expected


@pytest.mark.parametrize(
    ("nested_dict", "expected"),
    (
        (
            {"test": 1, "nested": {"if": True}},
            {"test": 1, "nested.if": True},
        ),
        (
            {"test": 1, "nested": {}},
            {"test": 1, "nested": "null"},
        ),
        (
            {"test": 1, "nested": []},
            {"test": 1, "nested": "null"},
        ),
        (
            {"test": 1, "list": [1, "2", 3.4]},
            {"test": 1, "list.0": 1, "list.1": "2", "list.2": 3.4},
        ),
        (
            {"test": 1, "level_1": {"level_2": {"works": True}, "test": 2}},
            {"test": 1, "level_1.level_2.works": True, "level_1.test": 2},
        ),
    ),
)
def test_flatten(nested_dict, expected):
    assert utils.flatten(dictionary=nested_dict) == expected


@pytest.mark.parametrize(
    ("data", "expected"),
    (
        ({"test": 1}, {"test": 1}),
        ({"nested": {"test": 1}}, {"nested": {"test": 1}}),
    ),
)
def test_write_json_object_to_file(data, expected, tmpdir):
    json_file_path = str(tmpdir.join("test_json.json"))
    utils.write_json_object_to_file(json_file_path, data)

    with open(json_file_path, mode="r") as handler:
        json.load(handler) == expected

    assert oct(os.stat(json_file_path).st_mode)[-4:].endswith("00")


class DummyPopenOutput(unit_tests.MockFunction):
    def __init__(self, output):
        self.call_count = 0
        self.output = output

    def __call__(self, args, stdout, stderr, bufsize):
        return self

    @property
    def stdout(self):
        return self

    def readline(self):
        try:
            next_line = self.output[self.call_count]
        except IndexError:
            return b""

        self.call_count += 1
        return next_line

    def communicate(self):
        pass

    def poll(self):
        return 0


def test_run_subprocess_env(monkeypatch):
    test_output = DummyPopenOutput([u"test of nonascii output: café".encode("utf-8")])
    monkeypatch.setattr(utils.subprocess, "Popen", test_output)

    output, rc = utils.run_subprocess(["echo", "foobar"])
    assert u"test of nonascii output: café" == output
    assert 0 == rc


class DummyGetUID(unit_tests.MockFunction):
    def __init__(self, uid):
        self.uid = uid

    def __call__(self, *args, **kargs):
        return self.uid


def test_require_root_is_not_root(monkeypatch, capsys):
    monkeypatch.setattr(os, "geteuid", DummyGetUID(1000))
    with pytest.raises(SystemExit):
        utils.require_root()

    assert "The tool needs to be run under the root user." in capsys.readouterr().out


def test_require_root_is_root(monkeypatch):
    monkeypatch.setattr(os, "geteuid", DummyGetUID(0))
    exit_mock = mock.Mock(return_value=1)
    monkeypatch.setattr(sys, "exit", exit_mock)
    utils.require_root()
    assert exit_mock.call_count == 0
