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
__metaclass__ = type

import os
import sys

from collections import namedtuple

import pytest
import six

import convert2rhel.toolopts
import convert2rhel.utils


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


def mock_cli_arguments(args):
    """
    Return a list of cli arguments where the first one is always the name of
    the executable, followed by 'args'.
    """
    return sys.argv[0:1] + args


class TestTooloptsParseFromCLI:
    def test_cmdline_interactive_username_without_passwd(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--username", "uname"]))
        convert2rhel.toolopts.CLI()
        assert global_tool_opts.username == "uname"

    def test_cmdline_interactive_passwd_without_uname(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--password", "passwd"]))
        convert2rhel.toolopts.CLI()
        assert global_tool_opts.password == "passwd"

    def test_cmdline_non_interactive_with_credentials(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--username", "uname", "--password", "passwd"]))
        convert2rhel.toolopts.CLI()
        assert global_tool_opts.username == "uname"
        assert global_tool_opts.password == "passwd"

    def test_cmdline_disablerepo_defaults_to_asterisk(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--enablerepo", "foo"]))
        convert2rhel.toolopts.CLI()
        assert global_tool_opts.enablerepo == ["foo"]
        assert global_tool_opts.disablerepo == ["*"]

    #
    # Parsing of serverurl
    #

    @pytest.mark.parametrize(
        ("serverurl", "hostname", "port", "prefix"),
        (
            ("https://rhsm.redhat.com:443/", "rhsm.redhat.com", "443", "/"),
            ("https://localhost/rhsm/", "localhost", None, "/rhsm/"),
            ("https://rhsm.redhat.com/", "rhsm.redhat.com", None, "/"),
            ("https://rhsm.redhat.com", "rhsm.redhat.com", None, None),
            ("https://rhsm.redhat.com:8443", "rhsm.redhat.com", "8443", None),
            ("subscription.redhat.com", "subscription.redhat.com", None, None),
        ),
    )
    def test_custom_serverurl(self, monkeypatch, global_tool_opts, serverurl, hostname, port, prefix):
        monkeypatch.setattr(
            sys,
            "argv",
            mock_cli_arguments(["--serverurl", serverurl, "--username", "User1", "--password", "Password1"]),
        )
        convert2rhel.toolopts.CLI()
        assert global_tool_opts.rhsm_hostname == hostname
        assert global_tool_opts.rhsm_port == port
        assert global_tool_opts.rhsm_prefix == prefix

    def test_no_serverurl(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments([]))
        convert2rhel.toolopts.CLI()
        assert global_tool_opts.rhsm_hostname is None
        assert global_tool_opts.rhsm_port is None
        assert global_tool_opts.rhsm_prefix is None

    @pytest.mark.parametrize(
        "serverurl",
        (
            "gopher://subscription.rhsm.redhat.com/",
            "https:///",
            "https://",
            "/",
        ),
    )
    def test_bad_serverurl(self, caplog, monkeypatch, global_tool_opts, serverurl):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--serverurl", serverurl, "-o", "MyOrg", "-k", "012335"]))

        with pytest.raises(SystemExit):
            convert2rhel.toolopts.CLI()

        message = (
            "Failed to parse a valid subscription-manager server from the --serverurl option.\n"
            "Please check for typos and run convert2rhel again with a corrected --serverurl.\n"
            "Supplied serverurl: %s\nError: " % serverurl
        )
        assert message in caplog.records[-1].message
        assert caplog.records[-1].levelname == "CRITICAL"

    def test_serverurl_with_no_rhsm(self, caplog, monkeypatch, global_tool_opts):
        monkeypatch.setattr(
            sys, "argv", mock_cli_arguments(["--serverurl", "localhost", "--no-rhsm", "--enablerepo", "testrepo"])
        )

        convert2rhel.toolopts.CLI()

        message = "Ignoring the --serverurl option. It has no effect when" " --disable-submgr or --no-rhsm is used."
        assert message in caplog.text

    def test_serverurl_with_no_rhsm_credentials(self, caplog, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--serverurl", "localhost"]))

        convert2rhel.toolopts.CLI()

        message = (
            "Ignoring the --serverurl option. It has no effect when no credentials to"
            " subscribe the system were given."
        )
        assert message in caplog.text

    def test_payg(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--payg"]))
        convert2rhel.toolopts.CLI()
        assert global_tool_opts.payg is True

    def test_no_payg(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments([]))
        convert2rhel.toolopts.CLI()
        assert global_tool_opts.payg is False


def test_keep_rhsm(monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--keep-rhsm"]))

    convert2rhel.toolopts.CLI()

    assert (
        "The --keep-rhsm option is deprecated and will be removed in"
        " the future. Convert2rhel will now always use the"
        " subscription-manager packages which are already installed on"
        " the system so this option has no effect." in caplog.text
    )


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
        pytest.param(
            mock_cli_arguments([]),
            "[subscription_manager]\nusername=conf_user\npassword=conf_pass\nactivation_key=conf_key\norg=conf_org",
            {"username": "conf_user", "password": "conf_pass", "activation_key": "conf_key", "org": "conf_org"},
            None,
            id="All values set in config",
        ),
        (
            mock_cli_arguments([]),
            "[subscription_manager]\npassword=conf_pass",
            {"password": "conf_pass", "activation_key": None},
            None,
        ),
        (
            mock_cli_arguments(["-p", "password"]),
            "[subscription_manager]\nactivation_key=conf_key",
            {"password": "password", "activation_key": None},
            "You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values.",
        ),
        (
            mock_cli_arguments(["-k", "activation_key", "-o", "org"]),
            "[subscription_manager]\nactivation_key=conf_key",
            {"password": None, "activation_key": "activation_key"},
            "You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values.",
        ),
        (
            mock_cli_arguments(["-k", "activation_key", "-o", "org"]),
            "[subscription_manager]\npassword=conf_pass",
            {"password": "conf_pass", "activation_key": "activation_key"},
            "You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values.",
        ),
        (
            mock_cli_arguments(["-k", "activation_key", "-p", "password", "-o", "org"]),
            "[subscription_manager]\npassword=conf_pass\nactivation_key=conf_key",
            {"password": "password", "activation_key": "activation_key"},
            "You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values.",
        ),
        (
            mock_cli_arguments(["-o", "org"]),
            "[subscription_manager]\npassword=conf_pass\nactivation_key=conf_key",
            {"password": "conf_pass", "activation_key": "conf_key"},
            "Either a password or an activation key can be used for system registration. We're going to use the"
            " activation key.",
        ),
        (
            mock_cli_arguments(["-u", "McLOVIN"]),
            "[subscription_manager]\nusername=NotMcLOVIN\n",
            {"username": "McLOVIN"},
            "You have passed the RHSM username through both the command line and"
            " the configuration file. We're going to use the command line values.",
        ),
        (
            mock_cli_arguments(["-o", "some-org"]),
            "[subscription_manager]\norg=a-different-org\nactivation_key=conf_key",
            {"org": "some-org"},
            "You have passed the RHSM org through both the command line and"
            " the configuration file. We're going to use the command line values.",
        ),
    ),
)
def test_config_file(argv, content, output, message, monkeypatch, tmpdir, caplog, global_tool_opts):
    # After each test there were left data from previous
    # Re-init needed delete the set data
    path = os.path.join(str(tmpdir), "convert2rhel.ini")
    with open(path, "w") as file:
        file.write(content)
    os.chmod(path, 0o600)

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(convert2rhel.toolopts, "CONFIG_PATHS", value=[path])
    convert2rhel.toolopts.CLI()

    if "activation_key" in output:
        assert convert2rhel.toolopts.tool_opts.activation_key == output["activation_key"]

    if "password" in output:
        assert convert2rhel.toolopts.tool_opts.password == output["password"]

    if "username" in output:
        assert convert2rhel.toolopts.tool_opts.username == output["username"]

    if "org" in output:
        assert convert2rhel.toolopts.tool_opts.org == output["org"]

    if message:
        print(caplog.text)
        assert message in caplog.text


@pytest.mark.parametrize(
    ("argv", "content", "message", "output"),
    (
        (
            mock_cli_arguments(["--password", "pass", "-f"]),
            "pass_file",
            "You have passed the RHSM password through both the --password-from-file and the --password option."
            " We're going to use the password from file.",
            {"password": "pass_file", "activation_key": None},
        ),
        (
            mock_cli_arguments(["--password", "pass", "--config-file"]),
            "[subscription_manager]\nactivation_key = key_cnf_file",
            "You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values.",
            {"password": "pass", "activation_key": None},
        ),
    ),
)
def test_multiple_auth_src_combined(argv, content, message, output, caplog, monkeypatch, tmpdir, global_tool_opts):
    """Test combination of password file or configuration file and CLI arguments."""
    path = os.path.join(str(tmpdir), "convert2rhel.file")
    with open(path, "w") as file:
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
            "You have passed the RHSM password through both the --password-from-file and the --password option."
            " We're going to use the password from file.",
            {"password": "pass_file", "activation_key": None},
        ),
    ),
)
def test_multiple_auth_src_files(argv, content, message, output, caplog, monkeypatch, tmpdir):
    """Test combination of password file, config file and CLI."""
    path0 = os.path.join(str(tmpdir), "convert2rhel.password")
    with open(path0, "w") as file:
        file.write(content[0])
    path1 = os.path.join(str(tmpdir), "convert2rhel.ini")
    with open(path1, "w") as file:
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
            mock_cli_arguments(["--password", "pass", "--activationkey", "key", "-o", "org"]),
            "Either a password or an activation key can be used for system registration."
            " We're going to use the activation key.",
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
            "[subscription_manager]\nusername = correct_username",
            {"username": "correct_username", "password": None, "activation_key": None, "org": None},
        ),
        (
            "[subscription_manager]\npassword = correct_password",
            {"username": None, "password": "correct_password", "activation_key": None, "org": None},
        ),
        pytest.param(
            "[subscription_manager]\n"
            "activation_key = correct_key\n"
            "Password = correct_password\n"
            "username = correct_username\n"
            "org = correct_org\n",
            {
                "username": "correct_username",
                "password": "correct_password",
                "activation_key": "correct_key",
                "org": "correct_org",
            },
            id="All options used together",
        ),
        (
            "[subscription_manager]\norg = correct_org",
            {"username": None, "password": None, "activation_key": None, "org": "correct_org"},
        ),
        (
            "[subscription_manager]\nincorrect_option = incorrect_content",
            {"username": None, "password": None, "activation_key": None, "org": None},
        ),
        (
            "[INVALID_HEADER]\nusername = correct_username\npassword = correct_password\nactivation_key = correct_key\norg = correct_org",
            {"username": None, "password": None, "activation_key": None, "org": None},
        ),
        (None, {"username": None, "password": None, "activation_key": None, "org": None}),
    ),
)
def test_options_from_config_files_default(content, output, monkeypatch, tmpdir, caplog):
    """Test config files in default path."""
    path = os.path.join(str(tmpdir), "convert2rhel.ini")
    if content:
        with open(path, "w") as file:
            file.write(content)
        os.chmod(path, 0o600)

    paths = ["/nonexisting/path", path]
    monkeypatch.setattr(convert2rhel.toolopts, "CONFIG_PATHS", value=paths)
    opts = convert2rhel.toolopts.options_from_config_files()

    assert opts["username"] == output["username"]
    assert opts["password"] == output["password"]
    assert opts["activation_key"] == output["activation_key"]
    assert opts["org"] == output["org"]

    if content:
        if "INVALID_HEADER" in content:
            assert "Unsupported header" in caplog.text
        if "incorrect_option" in content:
            assert "Unsupported option" in caplog.text


@pytest.mark.parametrize(
    ("content", "output", "content_lower_priority"),
    (
        (
            "[subscription_manager]\nusername = correct_username\nactivation_key = correct_key",
            {"username": "correct_username", "password": None, "activation_key": "correct_key", "org": None},
            "[subscription_manager]\nusername = low_prior_username",
        ),
        (
            "[subscription_manager]\nusername = correct_username\nactivation_key = correct_key",
            {"username": "correct_username", "password": None, "activation_key": "correct_key", "org": None},
            "[subscription_manager]\nactivation_key = low_prior_key",
        ),
        (
            "[subscription_manager]\nactivation_key = correct_key\norg = correct_org",
            {"username": None, "password": None, "activation_key": "correct_key", "org": "correct_org"},
            "[subscription_manager]\norg = low_prior_org",
        ),
        (
            "[subscription_manager]\nactivation_key = correct_key\nPassword = correct_password",
            {"username": None, "password": "correct_password", "activation_key": "correct_key", "org": None},
            "[subscription_manager]\npassword = low_prior_pass",
        ),
        (
            "[subscription_manager]\nactivation_key = correct_key\nPassword = correct_password",
            {"username": None, "password": "correct_password", "activation_key": "correct_key", "org": None},
            "[INVALID_HEADER]\npassword = low_prior_pass",
        ),
        (
            "[subscription_manager]\nactivation_key = correct_key\nPassword = correct_password",
            {"username": None, "password": "correct_password", "activation_key": "correct_key", "org": None},
            "[subscription_manager]\nincorrect_option = incorrect_option",
        ),
    ),
)
def test_options_from_config_files_specified(content, output, content_lower_priority, monkeypatch, tmpdir, caplog):
    """Test user specified path for config file."""
    path = os.path.join(str(tmpdir), "convert2rhel.ini")
    with open(path, "w") as file:
        file.write(content)
    os.chmod(path, 0o600)

    path_lower_priority = os.path.join(str(tmpdir), "convert2rhel_lower.ini")
    with open(path_lower_priority, "w") as file:
        file.write(content_lower_priority)
    os.chmod(path_lower_priority, 0o600)

    paths = [path_lower_priority]
    monkeypatch.setattr(convert2rhel.toolopts, "CONFIG_PATHS", value=paths)
    # user specified path
    opts = convert2rhel.toolopts.options_from_config_files(path)

    assert opts["username"] == output["username"]
    assert opts["password"] == output["password"]
    assert opts["activation_key"] == output["activation_key"]
    assert opts["org"] == output["org"]

    if "INVALID_HEADER" in content or "INVALID_HEADER" in content_lower_priority:
        assert "Unsupported header" in caplog.text
    if "incorrect_option" in content or "incorrect_option" in content_lower_priority:
        assert "Unsupported option" in caplog.text


@pytest.mark.parametrize(
    "supported_opts",
    (
        {
            "username": "correct_username",
            "password": "correct_password",
            "activation_key": "correct_key",
            "org": "correct_org",
        },
        {
            "username": "correct_username",
            "password": "correct_password",
            "activation_key": "correct_key",
            "org": "correct_org",
            "invalid_key": "invalid_key",
        },
    ),
)
def test_set_opts(supported_opts, global_tool_opts):
    convert2rhel.toolopts.ToolOpts.set_opts(global_tool_opts, supported_opts)

    assert global_tool_opts.username == supported_opts["username"]
    assert global_tool_opts.password == supported_opts["password"]
    assert global_tool_opts.activation_key == supported_opts["activation_key"]
    assert global_tool_opts.org == supported_opts["org"]
    assert not hasattr(global_tool_opts, "invalid_key")


UrlParts = namedtuple("UrlParts", ("scheme", "hostname", "port"))


@pytest.mark.parametrize(
    ("url_parts", "message"),
    (
        (
            UrlParts("gopher", "localhost", None),
            "Subscription manager must be accessed over http or https.  gopher is not valid",
        ),
        (UrlParts("http", None, None), "A hostname must be specified in a subscription-manager serverurl"),
        (UrlParts("http", "", None), "A hostname must be specified in a subscription-manager serverurl"),
    ),
)
def test_validate_serverurl_parsing(url_parts, message):
    with pytest.raises(ValueError, match=message):
        convert2rhel.toolopts._validate_serverurl_parsing(url_parts)


def test_log_command_used(caplog, monkeypatch):
    obfuscation_string = "*" * 5
    input_command = mock_cli_arguments(
        ["--username", "uname", "--password", "123", "--activationkey", "456", "--org", "789"]
    )
    expected_command = mock_cli_arguments(
        [
            "--username",
            obfuscation_string,
            "--password",
            obfuscation_string,
            "--activationkey",
            obfuscation_string,
            "--org",
            obfuscation_string,
        ]
    )
    monkeypatch.setattr(sys, "argv", input_command)
    convert2rhel.toolopts._log_command_used()

    assert " ".join(expected_command) in caplog.records[-1].message


@pytest.mark.parametrize(
    ("argv", "message"),
    (
        # The message is a log of used command
        (mock_cli_arguments(["-o", "org", "-k", "key"]), "-o ***** -k *****"),
        (
            mock_cli_arguments(["-o", "org"]),
            "Either the --organization or the --activationkey option is missing. You can't use one without the other.",
        ),
        (
            mock_cli_arguments(["-k", "key"]),
            "Either the --organization or the --activationkey option is missing. You can't use one without the other.",
        ),
    ),
)
def test_org_activation_key_specified(argv, message, monkeypatch, caplog, global_tool_opts):
    monkeypatch.setattr(sys, "argv", argv)

    try:
        convert2rhel.toolopts.CLI()
    except SystemExit:
        # Don't care about the exception, focus on output message
        pass
    assert message in caplog.text


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        (mock_cli_arguments(["convert"]), "conversion"),
        (mock_cli_arguments(["analyze"]), "analysis"),
        (mock_cli_arguments([]), "conversion"),
    ),
)
def test_pre_assessment_set(argv, expected, monkeypatch, global_tool_opts):
    monkeypatch.setattr(sys, "argv", argv)

    convert2rhel.toolopts.CLI()

    assert global_tool_opts.activity == expected


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        (
            mock_cli_arguments(["--disablerepo", "*", "--enablerepo", "*"]),
            "Duplicate repositories were found across disablerepo and enablerepo options",
        ),
        (
            mock_cli_arguments(
                ["--disablerepo", "*", "--disablerepo", "rhel-7-extras-rpm", "--enablerepo", "rhel-7-extras-rpm"]
            ),
            "Duplicate repositories were found across disablerepo and enablerepo options",
        ),
        (
            mock_cli_arguments(["--disablerepo", "test", "--enablerepo", "test"]),
            "Duplicate repositories were found across disablerepo and enablerepo options",
        ),
    ),
)
def test_disable_and_enable_repos_has_same_repo(argv, expected, monkeypatch, caplog, global_tool_opts):
    monkeypatch.setattr(sys, "argv", argv)
    convert2rhel.toolopts.CLI()

    assert expected in caplog.records[-1].message


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        (
            mock_cli_arguments(["--disablerepo", "*", "--enablerepo", "test"]),
            "Duplicate repositories were found across disablerepo and enablerepo options",
        ),
        (
            mock_cli_arguments(["--disablerepo", "test", "--enablerepo", "test1"]),
            "Duplicate repositories were found across disablerepo and enablerepo options",
        ),
    ),
)
def test_disable_and_enable_repos_with_different_repos(argv, expected, monkeypatch, caplog, global_tool_opts):
    monkeypatch.setattr(sys, "argv", argv)
    convert2rhel.toolopts.CLI()

    assert expected not in caplog.records[-1].message


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        ([], ["convert"]),
        (["--debug"], ["convert", "--debug"]),
        (["analyze", "--debug"], ["analyze", "--debug"]),
        (["--password=convert", "--debug"], ["convert", "--password=convert", "--debug"]),
    ),
)
def test_add_default_command(argv, expected, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    assert convert2rhel.toolopts._add_default_command(argv) == expected


@pytest.mark.parametrize(
    ("username", "password", "organization", "activation_key", "no_rhsm", "expected"),
    (
        ("User1", "Password1", None, None, False, True),
        (None, None, "My Org", "12345ABC", False, True),
        ("User1", "Password1", "My Org", "12345ABC", False, True),
        (None, None, None, None, True, False),
        ("User1", None, None, "12345ABC", False, False),
        (None, None, None, None, False, False),
        ("User1", "Password1", None, None, True, False),
    ),
)
def test_should_subscribe(username, password, organization, activation_key, no_rhsm, expected):
    t_opts = convert2rhel.toolopts.ToolOpts()
    t_opts.username = username
    t_opts.password = password
    t_opts.org = organization
    t_opts.activation_key = activation_key
    t_opts.no_rhsm = no_rhsm

    assert convert2rhel.toolopts._should_subscribe(t_opts) is expected
