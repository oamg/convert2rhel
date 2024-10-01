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

__metaclass__ = type

import getpass
import json
import logging
import os
import re
import shutil
import sys

from pickle import PicklingError

import pexpect
import pytest
import six

from convert2rhel.utils import prompt_user


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))

from six.moves import mock

from convert2rhel import exceptions, systeminfo, toolopts, unit_tests, utils  # Imports unit_tests/__init__.py
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests import RunCmdInPtyMocked, RunSubprocessMocked, conftest, is_rpm_based_os


DOWNLOADED_RPM_NVRA = "kernel-4.18.0-193.28.1.el8_2.x86_64"
DOWNLOADED_RPM_NEVRA = "7:{}".format(DOWNLOADED_RPM_NVRA)
DOWNLOADED_RPM_FILENAME = "{}.rpm".format(DOWNLOADED_RPM_NVRA)

YUMDOWNLOADER_OUTPUTS = (
    "{0}                  97% [================================================- ] 6.8 MB/s |  21 MB  00:00:00 ETA\n"
    "rpmdb time: 0.000\n"
    "{0}                                                                                    |  21 MB  00:00:01\n"
    "== Rebuilding _local repo. with 1 new packages ==".format(DOWNLOADED_RPM_FILENAME),
    "Last metadata expiration check: 2:47:36 ago on Thu 22 Oct 2020 06:07:08 PM CEST.\n"
    "{}         2.7 MB/s | 2.8 MB     00:01".format(DOWNLOADED_RPM_FILENAME),
    "/var/lib/convert2rhel/{} already exists and appears to be complete".format(DOWNLOADED_RPM_FILENAME),
    "rpmdb time: 0.000\nusing local copy of {}".format(DOWNLOADED_RPM_NEVRA),
    "rpmdb time: 0.000\nusing local copy of {}\r\n".format(DOWNLOADED_RPM_NEVRA),
    "[SKIPPED] {}: Already downloaded".format(DOWNLOADED_RPM_FILENAME),
)


class GetEUIDMocked(unit_tests.MockFunctionObject):
    spec = os.geteuid

    def __init__(self, uid, **kwargs):
        self.uid = uid
        super(GetEUIDMocked, self).__init__(**kwargs)

    def __call__(self, *args, **kwargs):
        super(GetEUIDMocked, self).__call__(*args, **kwargs)
        return self.uid


class FakeSecondCallToRunSubprocessMocked(RunSubprocessMocked):
    def __init__(self, second_call_return_code, *args, **kwargs):
        super(FakeSecondCallToRunSubprocessMocked, self).__init__(*args, **kwargs)
        self.real_run_subprocess = utils.run_subprocess
        self.second_call_return_code = second_call_return_code

    def __call__(self, *args, **kwargs):
        fake_return_val = super(FakeSecondCallToRunSubprocessMocked, self).__call__(*args, **kwargs)

        if self.call_count == 1:
            # Set this so it looks like run_subprocess failed on the next call
            self._mock.return_value = ("", self.second_call_return_code)
            return self.real_run_subprocess(*args, **kwargs)

        return fake_return_val


class DummyPopen:
    def __init__(self, *args, **kwargs):
        return

    @property
    def stdout(self):
        return self

    def readline(self):
        try:
            return next(self._output)
        except StopIteration:
            return b""

    def communicate(self):
        pass

    @property
    def returncode(self):
        return 0


@pytest.fixture
def dummy_popen_py3(request):
    output = unit_tests.get_pytest_marker(request, "popen_output")
    DummyPopen._output = (line.encode(encoding="utf-8") for line in output.args[0])
    return DummyPopen


@pytest.fixture
def dummy_popen_py2(request):
    output = unit_tests.get_pytest_marker(request, "popen_output")
    DummyPopen._output = (line.decode("utf-8").encode(encoding="utf-8") for line in output.args[0])
    return DummyPopen


def test_is_rpm_based_os():
    """This is testing a unit test function?"""
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
            [sys.executable, "-c", 'print({}("Ask for password: "))'.format(prompt_cmd)],
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


class FakeTransactionSet:
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
            "TransactionSet": FakeTransactionSet,
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
    class MockedRmtree:
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
        os.path.join(os.path.dirname(__file__), "../../data/version-independent/gpg-keys/RPM-GPG-KEY-redhat-release")
    )

    def test_find_keyid(self):
        assert utils.find_keyid(self.gpg_key) == "fd431d51"

    def test_find_keyid_race_in_gpg_cleanup(self, monkeypatch):
        """Test that we do not fail if gpg-agent removes the files once."""
        real_rmtree = shutil.rmtree
        monkeypatch.setattr(shutil, "rmtree", self.MockedRmtree(OSError(2, "File not found"), real_rmtree))

        assert utils.find_keyid(self.gpg_key) == "fd431d51"

    def test_find_keyid_race_while_removing_directory(self, caplog, monkeypatch):
        """Test that we do not fail if gpg-agent removes the files everytime."""
        exception = OSError(2, "File not found")
        monkeypatch.setattr(shutil, "rmtree", mock.Mock(spec=shutil.rmtree, side_effect=exception))

        assert utils.find_keyid(self.gpg_key) == "fd431d51"

        assert re.match(
            "Failed to remove temporary directory.*that held Red Hat gpg public keys.", caplog.records[-1].message
        )

    def test_find_keyid_gpg_bad_keyring_and_race_deleting_tmp_dir(self, caplog, monkeypatch):
        """Test that we do not fail with original error f gpg-agent removes the files."""
        monkeypatch.setattr(utils, "run_subprocess", FakeSecondCallToRunSubprocessMocked(second_call_return_code=1))
        exception = OSError(2, "File not found")
        monkeypatch.setattr(shutil, "rmtree", mock.Mock(spec=shutil.rmtree, side_effect=exception))

        with pytest.raises(
            utils.ImportGPGKeyError, match="Failed to read the temporary keyring with the rpm gpg key:.*"
        ):
            utils.find_keyid(self.gpg_key)

        assert re.match(
            "Failed to remove temporary directory.*that held Red Hat gpg public keys.", caplog.records[-1].message
        )

    def test_find_keyid_bad_file(self, tmpdir):
        gpg_key = os.path.join(str(tmpdir), "badkeyfile")
        with open(gpg_key, "w") as f:
            f.write("bad data\n")

        with pytest.raises(
            utils.ImportGPGKeyError, match="Failed to import the rpm gpg key into a temporary keyring.*"
        ):
            utils.find_keyid(gpg_key)

    def test_find_keyid_gpg_bad_keyring(self, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", FakeSecondCallToRunSubprocessMocked(second_call_return_code=1))

        with pytest.raises(
            utils.ImportGPGKeyError, match="Failed to read the temporary keyring with the rpm gpg key:.*"
        ):
            utils.find_keyid(self.gpg_key)

    def test_find_keyid_no_gpg_output(self, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", FakeSecondCallToRunSubprocessMocked(second_call_return_code=0))

        with pytest.raises(
            utils.ImportGPGKeyError,
            match="Unable to determine the gpg keyid for the rpm key file: {}".format(self.gpg_key),
        ):
            utils.find_keyid(self.gpg_key)

    def test_find_keyid_error_and_race_removing_directory(self, caplog, monkeypatch):
        """Test that we do not fail if gpg-agent removes the files."""
        exception = OSError(2, "File not found")
        monkeypatch.setattr(shutil, "rmtree", mock.Mock(spec=shutil.rmtree, side_effect=exception))

        utils.find_keyid(self.gpg_key)

        assert re.match(
            "Failed to remove temporary directory.*that held Red Hat gpg public keys.", caplog.records[-1].message
        )

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


class TestDownload_pkg:
    @pytest.fixture(autouse=True)
    def apply_cls_global_tool_opts(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(toolopts, "tool_opts", global_tool_opts)

    def test_download_pkgs(self, monkeypatch):
        monkeypatch.setattr(
            utils,
            "download_pkg",
            lambda pkg,
            dest,
            reposdir,
            enable_repos,
            disable_repos,
            set_releasever,
            custom_releasever,
            varsdir: "/filepath/",
        )

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

        assert paths == ["/filepath/", "/filepath/"]

    def test_download_pkg_success_with_all_params(self, monkeypatch):
        monkeypatch.setattr(system_info, "version", systeminfo.Version(8, 0))
        monkeypatch.setattr(system_info, "releasever", "8")
        monkeypatch.setattr(utils, "run_cmd_in_pty", RunCmdInPtyMocked())
        monkeypatch.setattr(
            utils,
            "get_rpm_path_from_yumdownloader_output",
            lambda x, y, z: "/path/test.rpm",
        )

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

        assert [
            "yumdownloader",
            "-v",
            "--setopt=exclude=",
            "--destdir={}".format(dest),
            "--setopt=reposdir={}".format(reposdir),
            "--disablerepo=*",
            "--enablerepo=repo1",
            "--enablerepo=repo2",
            "--releasever=8",
            "--setopt=varsdir=/tmp",
            "--setopt=module_platform_id=platform:el8",
            "kernel",
        ] == utils.run_cmd_in_pty.cmd

        assert path  # path is not None (which is the case of unsuccessful download)

    def test_download_pkg_assertion_error(self, monkeypatch):
        monkeypatch.setattr(system_info, "releasever", None)
        with pytest.raises(AssertionError, match="custom_releasever or system_info.releasever must be set."):
            utils.download_pkg(
                pkg="kernel",
                set_releasever=True,
                custom_releasever=None,
            )

    def test_download_pkg_failed_download_exit(self, monkeypatch):
        monkeypatch.setattr(system_info, "releasever", "7Server")
        monkeypatch.setattr(system_info, "version", systeminfo.Version(7, 0))
        monkeypatch.setattr(utils, "run_cmd_in_pty", RunCmdInPtyMocked(return_code=1))
        monkeypatch.setattr(os, "environ", {})

        with pytest.raises(SystemExit):
            utils.download_pkg("kernel")

    def test_download_pkg_failed_during_analysis_download_exit(self, monkeypatch):
        monkeypatch.setattr(system_info, "releasever", "7Server")
        monkeypatch.setattr(system_info, "version", systeminfo.Version(7, 0))
        monkeypatch.setattr(utils, "run_cmd_in_pty", RunCmdInPtyMocked(return_code=1))
        monkeypatch.setattr(os, "environ", {"CONVERT2RHEL_INCOMPLETE_ROLLBACK": "1"})
        monkeypatch.setattr(toolopts.tool_opts, "activity", "analysis")

        with pytest.raises(SystemExit):
            utils.download_pkg("kernel")

    def test_download_pkg_failed_download_overridden(self, monkeypatch):
        monkeypatch.setattr(system_info, "releasever", "7Server")
        monkeypatch.setattr(system_info, "version", systeminfo.Version(7, 0))
        monkeypatch.setattr(utils, "run_cmd_in_pty", RunCmdInPtyMocked(return_code=1))
        monkeypatch.setattr(os, "environ", {"CONVERT2RHEL_INCOMPLETE_ROLLBACK": "1"})
        monkeypatch.setattr(toolopts.tool_opts, "activity", "conversion")

        path = utils.download_pkg("kernel")

        assert path is None

    @pytest.mark.parametrize(
        ("output",),
        (
            ("bogus",),
            ("",),
        ),
    )
    def test_download_pkg_incorrect_output(self, output, monkeypatch, global_tool_opts):
        monkeypatch.setattr(system_info, "releasever", "7Server")
        monkeypatch.setattr(system_info, "version", systeminfo.Version(7, 0))
        monkeypatch.setattr(utils, "run_cmd_in_pty", RunCmdInPtyMocked(return_string=output))

        with pytest.raises(SystemExit):
            utils.download_pkg("kernel")


@pytest.mark.parametrize(("output",), [[out] for out in YUMDOWNLOADER_OUTPUTS])
def test_get_rpm_path_from_yumdownloader_output(output):
    path = utils.get_rpm_path_from_yumdownloader_output("cmd not important", output, utils.TMP_DIR)

    assert path == os.path.join(utils.TMP_DIR, DOWNLOADED_RPM_FILENAME)


@pytest.mark.parametrize(
    ("envvar", "activity", "should_raise", "message"),
    (
        (None, "conversion", True, "If you would rather disregard this check"),
        ("CONVERT2RHEL_INCOMPLETE_ROLLBACK", "conversion", False, "environment variable detected"),
        (None, "analysis", True, "you can choose to disregard this check"),
        ("CONVERT2RHEL_INCOMPLETE_ROLLBACK", "analysis", True, "you can choose to disregard this check"),
    ),
)
def test_report_on_a_download_error(envvar, activity, should_raise, message, monkeypatch, caplog, global_tool_opts):
    global_tool_opts.activity = activity
    monkeypatch.setattr(os, "environ", {envvar: "1"})

    if should_raise:
        with pytest.raises(SystemExit):
            utils.report_on_a_download_error("yd_output", "pkg_name")
    else:
        utils.report_on_a_download_error("yd_output", "pkg_name")

    assert message in caplog.records[-1].message


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


class TestRunSubprocess:
    @pytest.mark.parametrize(
        ("command", "expected"),
        (
            (
                ["echo", "foobar"],
                ("foobar\n", 0),
            ),
            # a command that just returns 56
            (
                ["sh", "-c", "exit 56"],
                ("", 56),
            ),
        ),
    )
    def test_run_subprocess(self, command, expected):
        output, code = utils.run_subprocess(command)

        assert (output, code) == expected

    @pytest.mark.skipif(sys.version_info < (3,), reason="python3 sets utf-8 by default")
    @pytest.mark.popen_output(["test of nonascii output: café"])
    def test_run_subprocess_env_utf8(self, dummy_popen_py3, monkeypatch):
        monkeypatch.setattr(utils.subprocess, "Popen", dummy_popen_py3)

        output, rc = utils.run_subprocess(["echo", "foobar"])
        assert "test of nonascii output: café" == output
        assert 0 == rc

    @pytest.mark.skipif(sys.version_info > (3,), reason="python2 sets ascii by default")
    @pytest.mark.popen_output(["test of nonascii output: café"])
    def test_run_subprocess_env_ascii(self, dummy_popen_py2, monkeypatch):
        monkeypatch.setattr(utils.subprocess, "Popen", dummy_popen_py2)

        output, rc = utils.run_subprocess(["echo", "foobar"])
        assert "test of nonascii output: café" == output.encode("utf-8")
        assert 0 == rc


def test_require_root_is_not_root(monkeypatch, caplog):
    monkeypatch.setattr(os, "geteuid", GetEUIDMocked(1000))
    with pytest.raises(SystemExit):
        utils.require_root()

    assert "The tool needs to be run under the root user." in caplog.text


def test_require_root_is_root(monkeypatch):
    monkeypatch.setattr(os, "geteuid", GetEUIDMocked(0))
    exit_mock = mock.Mock(return_value=1)
    monkeypatch.setattr(sys, "exit", exit_mock)
    utils.require_root()
    assert exit_mock.call_count == 0


class RunAsChildProcessFunctions:
    """Map methods as static to re-use in the run_as_child_process tests."""

    @staticmethod
    def raise_keyboard_interrupt_exception():
        raise KeyboardInterrupt

    @staticmethod
    def return_value():
        return 1

    @staticmethod
    def without_return():
        print("executed")

    @staticmethod
    def return_with_parameter(something):
        return something

    @staticmethod
    def return_with_both_args_and_kwargs(args, kwargs):
        return "{}, {}".format(args, kwargs)

    @staticmethod
    def raise_bare_system_exit_exception():
        raise SystemExit

    @staticmethod
    def raise_pickling_error_exception():
        raise PicklingError("pickling error")


@pytest.mark.parametrize(
    ("func", "args", "kwargs", "expected"),
    (
        (RunAsChildProcessFunctions.return_value, (), {}, 1),
        (RunAsChildProcessFunctions.without_return, (), {}, None),
        # Only args, no kwargs
        (
            RunAsChildProcessFunctions.return_with_parameter,
            ("Test",),
            {},
            "Test",
        ),
        # Only kwargs, no args
        (
            RunAsChildProcessFunctions.return_with_parameter,
            (),
            {"something": "Test"},
            "Test",
        ),
        # Both args and kwargs
        (
            RunAsChildProcessFunctions.return_with_both_args_and_kwargs,
            ("Test from args",),
            {"kwargs": "Test from kwargs"},
            "Test from args, Test from kwargs",
        ),
    ),
)
def test_run_as_child_process(func, args, kwargs, expected):
    decorated = utils.run_as_child_process(func)
    result = decorated(*args, **kwargs)

    assert result == expected
    assert hasattr(decorated, "__wrapped__")
    assert decorated.__wrapped__ == func


@pytest.mark.parametrize(
    ("func", "args", "kwargs", "expected_exception"),
    (
        (RunAsChildProcessFunctions.raise_bare_system_exit_exception, (), {}, SystemExit),
        (RunAsChildProcessFunctions.raise_pickling_error_exception, (), {}, PicklingError),
    ),
)
def test_run_as_child_process_with_exceptions(func, args, kwargs, expected_exception):
    decorated = utils.run_as_child_process(func)
    with pytest.raises(expected_exception):
        decorated(*args, **kwargs)


class MockProcess:
    def __init__(self, exception):
        self._exception = exception

    @property
    def pid(self):
        return 1000

    def __call__(self, *args, **kwargs):
        return self

    def start(self):
        pass

    def join(self):
        pass

    def is_alive(self):
        return True

    def terminate(self):
        pass

    @property
    def exception(self):
        return self._exception


def test_run_as_child_process_with_keyboard_interrupt(monkeypatch):
    monkeypatch.setattr(utils, "Process", MockProcess(KeyboardInterrupt))
    decorated = utils.run_as_child_process(RunAsChildProcessFunctions.raise_keyboard_interrupt_exception)
    with pytest.raises(KeyboardInterrupt):
        decorated((), {})


class TestRemovePkgs:
    def test_remove_pkgs_without_backup(self, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        pkgs = ["pkg1", "pkg2", "pkg3"]

        utils.remove_pkgs(pkgs, False)

        assert utils.run_subprocess.call_count == len(pkgs)

        rpm_remove_cmd = ["rpm", "-e", "--nodeps"]
        for cmd, pkg in zip(utils.run_subprocess.cmds, pkgs):
            assert rpm_remove_cmd + [pkg] == cmd

    @pytest.mark.parametrize(
        ("pkgs_to_remove", "ret_code", "critical", "expected"),
        (
            (["pkg1"], 1, True, "Error: Couldn't remove {0}."),
            (["pkg1"], 1, False, "Couldn't remove {0}."),
        ),
    )
    def test_remove_pkgs_failed_to_remove(
        self,
        pkgs_to_remove,
        ret_code,
        critical,
        expected,
        monkeypatch,
        caplog,
    ):
        run_subprocess_mock = RunSubprocessMocked(
            side_effect=unit_tests.run_subprocess_side_effect(
                (("rpm", "-e", "--nodeps", pkgs_to_remove[0]), ("test", ret_code)),
            )
        )
        monkeypatch.setattr(
            utils,
            "run_subprocess",
            value=run_subprocess_mock,
        )

        if critical:
            with pytest.raises(exceptions.CriticalError):
                utils.remove_pkgs(
                    pkgs_to_remove=pkgs_to_remove,
                    critical=critical,
                )
        else:
            utils.remove_pkgs(pkgs_to_remove=pkgs_to_remove, critical=critical)

        assert expected.format(pkgs_to_remove[0]) in caplog.records[-1].message

    def test_remove_pkgs_with_empty_list(self, caplog):
        utils.remove_pkgs([])
        assert "No package to remove" in caplog.messages[-1]


@pytest.mark.parametrize(
    ("pkg_nevra", "nvra_without_epoch"),
    (
        ("7:oraclelinux-release-7.9-1.0.9.el7.x86_64", "oraclelinux-release-7.9-1.0.9.el7.x86_64"),
        ("oraclelinux-release-8:8.2-1.0.8.el8.x86_64", "oraclelinux-release-8:8.2-1.0.8.el8.x86_64"),
        ("1:mod_proxy_html-2.4.6-97.el7.centos.5.x86_64", "mod_proxy_html-2.4.6-97.el7.centos.5.x86_64"),
        ("httpd-tools-2.4.6-97.el7.centos.5.x86_64", "httpd-tools-2.4.6-97.el7.centos.5.x86_64"),
    ),
)
def test_remove_epoch_from_yum_nevra_notation(pkg_nevra, nvra_without_epoch):
    assert utils._remove_epoch_from_yum_nevra_notation(pkg_nevra) == nvra_without_epoch


@pytest.mark.parametrize(
    ("env_name", "env_value", "tool_opts_name", "message"),
    (
        (
            "CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK",
            True,
            "skip_kernel_currency_check",
            "The environment variable CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK is deprecated and is set to be removed on Convert2RHEL 2.4.0.\n"
            "Please, use the configuration file instead.",
        ),
    ),
)
def test_warn_deprecated_env(global_tool_opts, monkeypatch, env_name, env_value, tool_opts_name, message, caplog):
    """Test setting the value based on env variable and it's logging."""
    monkeypatch.setattr(utils, "tool_opts", global_tool_opts)
    monkeypatch.setenv(env_name, env_value)

    utils.warn_deprecated_env(env_name)
    assert getattr(global_tool_opts, tool_opts_name) == str(env_value)
    assert caplog.records[-1].message == message


def test_warn_deprecated_env_wrong_name(global_tool_opts, monkeypatch, caplog):
    """Test when unsupported env variable is used, nothing is set."""
    monkeypatch.setattr(utils, "tool_opts", global_tool_opts)

    utils.warn_deprecated_env("UNSUPPORTED_ENV_VAR")

    # Get tool_opts with default values
    default_tool_opts = toolopts.ToolOpts()
    default_tool_opts.initialize(config_sources=[conftest.CliConfigMock(), conftest.FileConfigMock()])

    for item, value in global_tool_opts.__dict__.items():
        assert default_tool_opts.__dict__[item] == value
    assert not caplog.text
