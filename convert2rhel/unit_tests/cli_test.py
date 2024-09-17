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

import pytest
import six

from convert2rhel import cli, toolopts


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


def mock_cli_arguments(args):
    """
    Return a list of cli arguments where the first one is always the name of
    the executable, followed by 'args'.
    """
    return sys.argv[0:1] + args


@pytest.fixture(autouse=True)
def reset_tool_opts(monkeypatch):
    monkeypatch.setattr(cli, "tool_opts", toolopts.ToolOpts())


@pytest.fixture(autouse=True)
def apply_fileconfig_mock(monkeypatch):
    monkeypatch.setattr(cli, "FileConfig", mock.Mock())


class TestTooloptsParseFromCLI:
    def test_cmdline_interactive_username_without_passwd(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--username", "uname"]))
        cli.CLI()
        assert cli.tool_opts.username == "uname"

    def test_cmdline_interactive_passwd_without_uname(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--password", "passwd"]))
        cli.CLI()
        assert cli.tool_opts.password == "passwd"

    def test_cmdline_non_interactive_with_credentials(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--username", "uname", "--password", "passwd"]))
        cli.CLI()
        assert cli.tool_opts.username == "uname"
        assert cli.tool_opts.password == "passwd"

    def test_cmdline_disablerepo_defaults_to_asterisk(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(cli, "tool_opts", global_tool_opts)
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--enablerepo", "foo"]))
        cli.CLI()
        assert cli.tool_opts.enablerepo == ["foo"]
        assert cli.tool_opts.disablerepo == ["*"]

    # Parsing of serverurl

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
        monkeypatch.setattr(cli, "tool_opts", global_tool_opts)
        monkeypatch.setattr(
            sys,
            "argv",
            mock_cli_arguments(["--serverurl", serverurl, "--username", "User1", "--password", "Password1"]),
        )
        cli.CLI()
        assert global_tool_opts.rhsm_hostname == hostname
        assert global_tool_opts.rhsm_port == port
        assert global_tool_opts.rhsm_prefix == prefix

    def test_no_serverurl(self, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments([]))
        cli.CLI()
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
    def test_bad_serverurl(self, caplog, monkeypatch, serverurl):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--serverurl", serverurl, "-o", "MyOrg", "-k", "012335"]))

        with pytest.raises(SystemExit):
            cli.CLI()

        message = (
            "Failed to parse a valid subscription-manager server from the --serverurl option.\n"
            "Please check for typos and run convert2rhel again with a corrected --serverurl.\n"
            "Supplied serverurl: %s\nError: " % serverurl
        )
        assert message in caplog.records[-1].message
        assert caplog.records[-1].levelname == "CRITICAL"

    def test_serverurl_with_no_rhsm(self, caplog, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", mock_cli_arguments(["--serverurl", "localhost", "--no-rhsm", "--enablerepo", "testrepo"])
        )

        cli.CLI()

        message = "Ignoring the --serverurl option. It has no effect when --no-rhsm is used."
        assert message in caplog.text

    def test_serverurl_with_no_rhsm_credentials(self, caplog, monkeypatch):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--serverurl", "localhost"]))

        cli.CLI()

        message = (
            "Ignoring the --serverurl option. It has no effect when no credentials to"
            " subscribe the system were given."
        )
        assert message in caplog.text


def test_no_rhsm_option_system_exit_exception(monkeypatch, global_tool_opts):
    monkeypatch.setattr(cli, "tool_opts", global_tool_opts)
    monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--no-rhsm"]))

    with pytest.raises(SystemExit, match="The --enablerepo option is required when --no-rhsm is used."):
        cli.CLI()


@pytest.mark.parametrize(
    ("argv", "no_rhsm_value"),
    ((mock_cli_arguments(["--no-rhsm", "--enablerepo", "test_repo"]), True),),
)
def test_no_rhsm_option_work(argv, no_rhsm_value, monkeypatch, global_tool_opts):
    monkeypatch.setattr(cli, "tool_opts", global_tool_opts)
    monkeypatch.setattr(sys, "argv", argv)

    cli.CLI()

    assert global_tool_opts.enablerepo == ["test_repo"]
    assert global_tool_opts.no_rhsm == no_rhsm_value


@pytest.mark.parametrize(
    ("argv", "content", "output", "message"),
    (
        pytest.param(
            mock_cli_arguments([]),
            """\
[subscription_manager]
username                         = conf_user
password                         = conf_pass
activation_key                   = conf_key
org                              = conf_org

[host_metering]
configure_host_metering          = 0

[inhibitor_overrides]
incomplete_rollback              = 0
tainted_kernel_module_check_skip = 0
outdated_package_check_skip      = 0
allow_older_version              = 0
allow_unavailable_kmods          = 0
skip_kernel_currency_check       = 0
            """,
            {
                "username": "conf_user",
                "password": "conf_pass",
                "activation_key": "conf_key",
                "org": "conf_org",
                "configure_host_metering": False,
                "incomplete_rollback": False,
                "tainted_kernel_module_check_skip": False,
                "outdated_package_skip": False,
                "allow_older_version": False,
                "allow_unavailable_kmods": False,
                "skip_kernel_currency_check": False,
            },
            None,
            id="All values set in config",
        ),
        (
            mock_cli_arguments([]),
            """\
[subscription_manager]
password = conf_pass
            """,
            {"password": "conf_pass"},
            None,
        ),
        (
            mock_cli_arguments([]),
            """\
[subscription_manager]
password = conf_pass

[inhibitor_overrides]
incomplete_rollback = 1
            """,
            {"password": "conf_pass", "incomplete_rollback": True},
            None,
        ),
        (
            mock_cli_arguments(["-p", "password"]),
            """\
[subscription_manager]
activation_key = conf_key
            """,
            {"password": "password"},
            None,
        ),
        (
            mock_cli_arguments(["-k", "activation_key", "-o", "org"]),
            """\
[subscription_manager]
activation_key = conf_key
            """,
            {"activation_key": "activation_key", "org": "org"},
            "You have passed the RHSM activation key through both the command line and the"
            " configuration file. We're going to use the command line values.",
        ),
        (
            mock_cli_arguments(["-k", "activation_key", "-o", "org"]),
            """\
[subscription_manager]
password = conf_pass
            """,
            {"password": "conf_pass", "activation_key": "activation_key"},
            None,
        ),
        (
            mock_cli_arguments(["-k", "activation_key", "-p", "password", "-o", "org"]),
            """\
[subscription_manager]
password = conf_pass
activation_key = conf_key
            """,
            {"password": "password"},
            "You have passed the RHSM password without an associated username. Please provide a username together with the password.",
        ),
        (
            mock_cli_arguments(["-o", "org"]),
            """\
[subscription_manager]
password = conf_pass
activation_key = conf_key
            """,
            {"password": "conf_pass", "activation_key": "conf_key", "org": "org"},
            "Either a password or an activation key can be used for system registration. We're going to use the"
            " activation key.",
        ),
        (
            mock_cli_arguments(["-u", "McLOVIN"]),
            """\
[subscription_manager]
username = NotMcLOVIN
            """,
            {"username": "McLOVIN"},
            "You have passed the RHSM username through both the command line and"
            " the configuration file. We're going to use the command line values.",
        ),
        (
            mock_cli_arguments(["-o", "some-org"]),
            """\
[subscription_manager]
org = a-different-org
activation_key = conf_key
            """,
            {"org": "some-org"},
            "You have passed the RHSM org through both the command line and"
            " the configuration file. We're going to use the command line values.",
        ),
    ),
)
def test_config_file(argv, content, output, message, monkeypatch, tmpdir, caplog):
    # After each test there were left data from previous
    # Re-init needed delete the set data
    path = os.path.join(str(tmpdir), "convert2rhel.ini")
    with open(path, "w") as file:
        file.write(content)
    os.chmod(path, 0o600)

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(cli, "FileConfig", toolopts.config.FileConfig)
    monkeypatch.setattr(toolopts.config.FileConfig, "DEFAULT_CONFIG_FILES", value=[path])
    cli.CLI()

    if "activation_key" in output:
        assert cli.tool_opts.activation_key == output["activation_key"]

    if "password" in output:
        assert cli.tool_opts.password == output["password"]

    if "username" in output:
        assert cli.tool_opts.username == output["username"]

    if "org" in output:
        assert cli.tool_opts.org == output["org"]

    if message:
        assert message in caplog.text


@pytest.mark.parametrize(
    ("argv", "content", "message", "output"),
    (
        (
            mock_cli_arguments(["--password", "pass", "--config-file"]),
            "[subscription_manager]\nactivation_key = key_cnf_file",
            "You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values.",
            {"password": "pass", "activation_key": None},
        ),
    ),
)
def test_multiple_auth_src_combined(argv, content, message, output, caplog, monkeypatch, tmpdir):
    """Test combination of password file or configuration file and CLI arguments."""
    path = os.path.join(str(tmpdir), "convert2rhel.file")
    with open(path, "w") as file:
        file.write(content)
    os.chmod(path, 0o600)
    # The path for file is the last argument
    argv.append(path)

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(cli, "FileConfig", toolopts.config.FileConfig)
    monkeypatch.setattr(toolopts.config.FileConfig, "DEFAULT_CONFIG_FILES", value=[path])
    cli.CLI()

    assert message in caplog.text
    assert cli.tool_opts.activation_key == output["activation_key"]
    assert cli.tool_opts.password == output["password"]


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
    cli.CLI()

    assert message in caplog.text
    assert cli.tool_opts.activation_key == output["activation_key"]
    assert cli.tool_opts.password == output["password"]


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
    cli._log_command_used()

    assert " ".join(expected_command) in caplog.records[-1].message


@pytest.mark.parametrize(
    ("argv", "message"),
    (
        (
            mock_cli_arguments(["-o", "org"]),
            "Either the --org or the --activationkey option is missing. You can't use one without the other.",
        ),
        (
            mock_cli_arguments(["-k", "key"]),
            "Either the --org or the --activationkey option is missing. You can't use one without the other.",
        ),
    ),
)
def test_org_activation_key_specified(argv, message, monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", argv)

    try:
        cli.CLI()
    except SystemExit:
        # Don't care about the exception, focus on output message
        pass

    assert message in caplog.records[-1].message


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        (mock_cli_arguments(["convert"]), "conversion"),
        (mock_cli_arguments(["analyze"]), "analysis"),
        (mock_cli_arguments([]), "conversion"),
    ),
)
def test_pre_assessment_set(argv, expected, monkeypatch, global_tool_opts):
    monkeypatch.setattr(cli, "tool_opts", global_tool_opts)
    monkeypatch.setattr(sys, "argv", argv)

    cli.CLI()

    assert cli.tool_opts.activity == expected


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
def test_disable_and_enable_repos_has_same_repo(argv, expected, monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", argv)
    cli.CLI()

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
def test_disable_and_enable_repos_with_different_repos(argv, expected, monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", argv)
    cli.CLI()

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
    assert cli._add_default_command(argv) == expected


@pytest.mark.parametrize(
    ("argv", "message"),
    (
        (
            mock_cli_arguments(["analyze", "--no-rpm-va"]),
            "We will proceed with ignoring the --no-rpm-va option as running rpm -Va in the analysis mode is essential for a complete rollback to the original system state at the end of the analysis.",
        ),
    ),
)
def test_override_no_rpm_va_setting(monkeypatch, argv, message, caplog):
    monkeypatch.setattr(sys, "argv", argv)
    cli.CLI()

    assert caplog.records[-1].message == message
    assert not cli.tool_opts.no_rpm_va


def test_critical_exit_no_rpm_va_setting(monkeypatch, global_tool_opts, tmpdir):
    # After each test there were left data from previous
    # Re-init needed delete the set data
    path = os.path.join(str(tmpdir), "convert2rhel.ini")
    with open(path, "w") as file:
        content = ""
        file.write(content)

    os.chmod(path, 0o600)

    monkeypatch.setattr(cli, "tool_opts", global_tool_opts)
    monkeypatch.setattr(cli, "FileConfig", toolopts.config.FileConfig)
    monkeypatch.setattr(toolopts.config.FileConfig, "DEFAULT_CONFIG_FILES", value=[path])
    monkeypatch.setattr(cli, "tool_opts", global_tool_opts)
    monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--no-rpm-va"]))
    with pytest.raises(
        SystemExit,
        match="We need to run the 'rpm -Va' command to be able to perform a complete rollback of changes done to the system during the pre-conversion analysis. If you accept the risk of an incomplete rollback, set the CONVERT2RHEL_INCOMPLETE_ROLLBACK=1 environment variable. Otherwise, remove the --no-rpm-va option.",
    ):
        cli.CLI()

    assert cli.tool_opts.no_rpm_va


@pytest.mark.parametrize(
    ("argv", "expected", "message"),
    (
        (
            ["analyze", "--no-rpm-va"],
            False,
            "We will proceed with ignoring the --no-rpm-va option as running rpm -Va in the analysis mode is essential for a complete rollback to the original system state at the end of the analysis.",
        ),
        (["--no-rpm-va"], True, ""),
    ),
)
def test_setting_no_rpm_va(argv, expected, message, monkeypatch, caplog, tmpdir):
    # After each test there were left data from previous
    # Re-init needed delete the set data
    path = os.path.join(str(tmpdir), "convert2rhel.ini")
    with open(path, "w") as file:
        content = """\
[inhibitor_overrides]
incomplete_rollback = "1"
"""
        file.write(content)

    os.chmod(path, 0o600)

    monkeypatch.setattr(cli, "FileConfig", toolopts.config.FileConfig)
    monkeypatch.setattr(toolopts.config.FileConfig, "DEFAULT_CONFIG_FILES", value=[path])
    monkeypatch.setattr(sys, "argv", mock_cli_arguments(argv))

    cli.CLI()

    assert cli.tool_opts.no_rpm_va == expected
    assert cli.tool_opts.incomplete_rollback

    if message:
        assert caplog.records[-1].message == message


@pytest.mark.parametrize(
    ("argv", "message"),
    (
        # The message is a log of used command
        (mock_cli_arguments(["-u", "user", "-p", "pass"]), "-u ***** -p *****"),
        (
            mock_cli_arguments(["-p", "pass"]),
            "You have passed the RHSM password without an associated username. Please provide a username together with the password",
        ),
        (
            mock_cli_arguments(["-u", "user"]),
            "You have passed the RHSM username without an associated password. Please provide a password together with the username",
        ),
    ),
)
def test_cli_userpass_specified(argv, message, monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", argv)

    try:
        cli.CLI()
    except SystemExit:
        # Don't care about the exception, focus on output message
        pass
    assert message in caplog.text


@pytest.mark.parametrize(
    ("activation_key", "organization", "argv"),
    (
        ("activation_key", "org", ["analyze", "-u name", "-p pass"]),
        (None, None, ["analyze", "-u name", "-p pass"]),
    ),
)
def test_cli_args_config_file_cornercase(activation_key, organization, argv, monkeypatch, global_tool_opts):
    monkeypatch.setattr(sys, "argv", mock_cli_arguments(argv))
    global_tool_opts.org = organization
    global_tool_opts.activation_key = activation_key
    global_tool_opts.no_rhsm = True
    monkeypatch.setattr(toolopts, "tool_opts", global_tool_opts)

    # Make sure it doesn't raise an exception
    cli.CLI()
