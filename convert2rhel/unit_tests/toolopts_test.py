# -*- coding: utf-8 -*-
#
# Copyright(C) 2016 Red Hat, Inc.
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

# Required imports:


import os
import sys
import unittest

import pytest
import six

import convert2rhel.toolopts
import convert2rhel.utils

from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel.toolopts import tool_opts


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


def mock_cli_arguments(args):
    """Return a list of cli arguments where the first one is always the name of the executable, followed by 'args'."""
    return sys.argv[0:1] + args


class TestToolopts(unittest.TestCase):
    def setUp(self):
        tool_opts.__init__()

    @unit_tests.mock(sys, "argv", mock_cli_arguments(["--username", "uname"]))
    def test_cmdline_interactive_username_without_passwd(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.username, "uname")
        self.assertFalse(tool_opts.credentials_thru_cli)

    @unit_tests.mock(sys, "argv", mock_cli_arguments(["--password", "passwd"]))
    def test_cmdline_interactive_passwd_without_uname(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.password, "passwd")
        self.assertFalse(tool_opts.credentials_thru_cli)

    @unit_tests.mock(
        sys,
        "argv",
        mock_cli_arguments(["--username", "uname", "--password", "passwd"]),
    )
    def test_cmdline_non_ineractive_with_credentials(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.username, "uname")
        self.assertEqual(tool_opts.password, "passwd")
        self.assertTrue(tool_opts.credentials_thru_cli)

    @unit_tests.mock(sys, "argv", mock_cli_arguments(["--serverurl", "url"]))
    def test_custom_serverurl(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.serverurl, "url")

    @unit_tests.mock(sys, "argv", mock_cli_arguments(["--enablerepo", "foo"]))
    def test_cmdline_disablerepo_defaults_to_asterisk(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.enablerepo, ["foo"])
        self.assertEqual(tool_opts.disablerepo, ["*"])


@pytest.mark.parametrize(
    ("argv", "warn", "keep_rhsm_value"),
    (
        (mock_cli_arguments(["--keep-rhsm"]), False, True),
        (mock_cli_arguments(["--keep-rhsm", "--disable-submgr", "--enablerepo", "test_repo"]), True, False),
    ),
)
@mock.patch("convert2rhel.toolopts.tool_opts.keep_rhsm", False)
def test_keep_rhsm(argv, warn, keep_rhsm_value, monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", argv)
    convert2rhel.toolopts.CLI()
    if warn:
        assert "Ignoring the --keep-rhsm option" in caplog.text
    else:
        assert "Ignoring the --keep-rhsm option" not in caplog.text
    assert convert2rhel.toolopts.tool_opts.keep_rhsm == keep_rhsm_value


@pytest.mark.parametrize(
    ("argv", "warn", "ask_to_continue"),
    (
        (mock_cli_arguments(["-v", "Server"]), True, True),
        (mock_cli_arguments(["--variant", "Client"]), True, True),
        (mock_cli_arguments(["-v"]), True, True),
        (mock_cli_arguments(["--variant"]), True, True),
        (mock_cli_arguments(["--version"]), False, False),
        (mock_cli_arguments([]), False, False),
    ),
)
def test_cmdline_obsolete_variant_option(argv, warn, ask_to_continue, monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(convert2rhel.utils, "ask_to_continue", mock.Mock())
    convert2rhel.toolopts.warn_on_unsupported_options()
    if warn:
        assert "variant option is not supported" in caplog.text
    else:
        assert "variant option is not supported" not in caplog.text
    if ask_to_continue:
        convert2rhel.utils.ask_to_continue.assert_called_once()
    else:
        convert2rhel.utils.ask_to_continue.assert_not_called()


@pytest.mark.parametrize(
    ("argv", "raise_exception", "no_rhsm_value"),
    (
        (mock_cli_arguments(["--disable-submgr"]), True, True),
        (mock_cli_arguments(["--no-rhsm"]), True, True),
        (mock_cli_arguments(["--disable-submgr", "--enablerepo", "test_repo"]), False, True),
        (mock_cli_arguments(["--no-rhsm", "--disable-submgr", "--enablerepo", "test_repo"]), False, True),
    ),
)
@mock.patch("convert2rhel.toolopts.tool_opts.no_rhsm", False)
@mock.patch("convert2rhel.toolopts.tool_opts.enablerepo", [])
def test_both_disable_submgr_and_no_rhsm_options_work(argv, raise_exception, no_rhsm_value, monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", argv)

    if raise_exception:
        with pytest.raises(SystemExit):
            convert2rhel.toolopts.CLI()
            assert "The --enablerepo option is required when --disable-submgr or --no-rhsm is used." in caplog.text
    else:
        convert2rhel.toolopts.CLI()

    assert convert2rhel.toolopts.tool_opts.no_rhsm == no_rhsm_value


@pytest.mark.parametrize(
    ("argv", "content", "output", "message"),
    (
        (
            mock_cli_arguments([""]),
            "[subscription_manager]\npassword=conf_pass",
            {"password": "conf_pass", "activation_key": None},
            None,
        ),
        (
            mock_cli_arguments(["-p", "password"]),
            "[subscription_manager]\nactivation_key=conf_key",
            {"password": "password", "activation_key": None},
            "Command line authentication method take precedence over method in configuration file.",
        ),
        (
            mock_cli_arguments(["-k", "activation_key"]),
            "[subscription_manager]\nactivation_key=conf_key",
            {"password": None, "activation_key": "activation_key"},
            "Command line authentication method take precedence over method in configuration file.",
        ),
        (
            mock_cli_arguments(["-k", "activation_key"]),
            "[subscription_manager]\npassword=conf_pass",
            {"password": "conf_pass", "activation_key": "activation_key"},
            "Command line authentication method take precedence over method in configuration file.",
        ),
        (
            mock_cli_arguments(["-k", "activation_key", "-p", "password"]),
            "[subscription_manager]\npassword=conf_pass\nactivation_key=conf_key",
            {"password": "password", "activation_key": "activation_key"},
            "Command line authentication method take precedence over method in configuration file.",
        ),
        (
            mock_cli_arguments([""]),
            "[subscription_manager]\npassword=conf_pass\nactivation_key=conf_key",
            {"password": "conf_pass", "activation_key": "conf_key"},
            "Set only one of password or activation key. Activation key take precedence.",
        ),
    ),
)
def test_config_file(argv, content, output, message, monkeypatch, tmp_path, caplog):
    # After each test there were left data from previous
    # Re-init needed delete the set data
    convert2rhel.toolopts.tool_opts.__init__()
    path = os.path.join(str(tmp_path), "convert2rhel.ini")
    with open(path, "w") as file:  # pylint: disable=unspecified-encoding
        file.write(content)
    os.chmod(path, 0o600)

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(convert2rhel.toolopts, "CONFIG_PATHS", value=[path])
    convert2rhel.toolopts.CLI()

    assert convert2rhel.toolopts.tool_opts.activation_key == output["activation_key"]
    assert convert2rhel.toolopts.tool_opts.password == output["password"]
    if message:
        assert message in caplog.text


@pytest.mark.parametrize(
    ("argv", "content", "message", "output"),
    (
        (
            mock_cli_arguments(["--password", "pass", "-f"]),
            "pass_file",
            "Password file argument take precedence over the password argument.",
            {"password": "pass_file", "activation_key": None},
        ),
        (
            mock_cli_arguments(["--password", "pass", "--config-file"]),
            "[subscription_manager]\nactivation_key = key_cnf_file",
            "Command line authentication method take precedence over method in configuration file.",
            {"password": "pass", "activation_key": None},
        ),
    ),
)
def test_multiple_auth_src_combined(argv, content, message, output, caplog, monkeypatch, tmp_path):
    """Test combination of password file or configuration file and CLI arguments."""
    convert2rhel.toolopts.tool_opts.__init__()
    path = os.path.join(str(tmp_path), "convert2rhel.file")
    with open(path, "w") as file:  # pylint: disable=unspecified-encoding
        file.write(content)
    os.chmod(path, 0o600)
    # The path for file is the last argument
    argv.append(path)

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(convert2rhel.toolopts, "CONFIG_PATHS", value=[""])
    convert2rhel.toolopts.CLI()

    assert message in caplog.text
    assert convert2rhel.toolopts.tool_opts.activation_key == output["activation_key"]
    assert convert2rhel.toolopts.tool_opts.password == output["password"]


@pytest.mark.parametrize(
    ("argv", "content", "message", "output"),
    (
        (
            mock_cli_arguments(["--password", "pass", "-f", "file", "--config-file", "file"]),
            ("pass_file", "[subscription_manager]\nactivation_key = pass_cnf_file"),
            "Password file take precedence over the config file.",
            {"password": "pass_file", "activation_key": None},
        ),
    ),
)
def test_multiple_auth_src_files(argv, content, message, output, caplog, monkeypatch, tmp_path):
    """Test combination of password file, config file and CLI."""
    path0 = os.path.join(str(tmp_path), "convert2rhel.password")
    with open(path0, "w") as file:  # pylint: disable=unspecified-encoding
        file.write(content[0])
    path1 = os.path.join(str(tmp_path), "convert2rhel.ini")
    with open(path1, "w") as file:  # pylint: disable=unspecified-encoding
        file.write(content[1])
    # Set the paths
    argv[-3] = path0
    argv[-1] = path1
    os.chmod(path1, 0o600)

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(convert2rhel.toolopts, "CONFIG_PATHS", value=[""])
    convert2rhel.toolopts.CLI()

    assert message in caplog.text
    assert convert2rhel.toolopts.tool_opts.activation_key == output["activation_key"]
    assert convert2rhel.toolopts.tool_opts.password == output["password"]


@pytest.mark.parametrize(
    ("argv", "message", "output"),
    (
        (
            mock_cli_arguments(["--password", "pass", "--activationkey", "key"]),
            "Set only one of password or activation key.",
            {"password": "pass", "activation_key": "key"},
        ),
    ),
)
def test_multiple_auth_src_cli(argv, message, output, caplog, monkeypatch):
    """Test both auth methods in CLI."""
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(convert2rhel.toolopts, "CONFIG_PATHS", value=[""])
    convert2rhel.toolopts.CLI()

    assert message in caplog.text
    assert convert2rhel.toolopts.tool_opts.activation_key == output["activation_key"]
    assert convert2rhel.toolopts.tool_opts.password == output["password"]


@pytest.mark.parametrize(
    ("content", "output"),
    (
        (
            "[subscription_manager]\npassword = correct_password",
            {"password": "correct_password", "activation_key": None},
        ),
        (
            "[subscription_manager]\nactivation_key = correct_key\nPassword = correct_password",
            {"password": "correct_password", "activation_key": "correct_key"},
        ),
        (
            "[subscription_manager]\nincorrect_option = incorrect_content",
            {"password": None, "activation_key": None},
        ),
        ("[INVALID_HEADER]\nactivation_key = correct_key", {"password": None, "activation_key": None}),
        (None, {"password": None, "activation_key": None}),
    ),
)
def test_options_from_config_files_default(content, output, monkeypatch, tmp_path, caplog):
    """Test config files in default path."""
    path = os.path.join(str(tmp_path), "convert2rhel.ini")
    if content:
        with open(path, "w") as file:  # pylint: disable=unspecified-encoding
            file.write(content)
        os.chmod(path, 0o600)

    paths = ["/nonexisting/path", path]
    monkeypatch.setattr(convert2rhel.toolopts, "CONFIG_PATHS", value=paths)
    opts = convert2rhel.toolopts.options_from_config_files()

    assert opts["password"] == output["password"]
    assert opts["activation_key"] == output["activation_key"]
    if content:
        if "INVALID_HEADER" in content:
            assert "Unsupported header" in caplog.text
        if "incorrect_option" in content:
            assert "Unsupported option" in caplog.text


@pytest.mark.parametrize(
    ("content", "output", "content_lower_priority"),
    (
        (
            "[subscription_manager]\nactivation_key = correct_key\nPassword = correct_password",
            {"password": "correct_password", "activation_key": "correct_key"},
            "[subscription_manager]\npassword = low_prior_pass",
        ),
        (
            "[subscription_manager]\nactivation_key = correct_key\nPassword = correct_password",
            {"password": "correct_password", "activation_key": "correct_key"},
            "[INVALID_HEADER]\nincorrect_option = incorrect_option",
        ),
        (
            "[subscription_manager]\nactivation_key = correct_key\nPassword = correct_password",
            {"password": "correct_password", "activation_key": "correct_key"},
            "[subscription_manager]\nincorrect_option = incorrect_option",
        ),
    ),
)
def test_options_from_config_files_specified(content, output, content_lower_priority, monkeypatch, tmp_path, caplog):
    """Test user specified path for config file."""
    path = os.path.join(str(tmp_path), "convert2rhel.ini")
    with open(path, "w") as file:  # pylint: disable=unspecified-encoding
        file.write(content)
    os.chmod(path, 0o600)

    path_lower_priority = os.path.join(str(tmp_path), "convert2rhel_lower.ini")
    content_lower_priority = "[subscription_manager]\npassword = low_prior_pass"
    with open(path_lower_priority, "w") as file:  # pylint: disable=unspecified-encoding
        file.write(content_lower_priority)
    os.chmod(path_lower_priority, 0o600)

    paths = [path_lower_priority]
    monkeypatch.setattr(convert2rhel.toolopts, "CONFIG_PATHS", value=paths)
    # user specified path
    opts = convert2rhel.toolopts.options_from_config_files(path)

    assert opts["password"] == output["password"]
    assert opts["activation_key"] == output["activation_key"]
    if "INVALID_HEADER" in content or "INVALID_HEADER" in content_lower_priority:
        assert "Unsupported header" in caplog.text
    if "incorrect_option" in content or "incorrect_option" in content_lower_priority:
        assert "Unsupported option" in caplog.text


@pytest.mark.parametrize(
    "supported_opts",
    (
        {"password": "correct_password", "activation_key": "correct_key"},
        {"password": "correct_password", "activation_key": "correct_key", "invalid_key": "invalid_key"},
    ),
)
def test_set_opts(supported_opts):
    tool_opts.__init__()
    convert2rhel.toolopts.ToolOpts.set_opts(tool_opts, supported_opts)

    assert tool_opts.password == supported_opts["password"]
    assert tool_opts.activation_key == supported_opts["activation_key"]
    assert not hasattr(tool_opts, "invalid_key")
