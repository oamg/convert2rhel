import os
import sys

from collections import namedtuple

import pytest
import six

from convert2rhel import cli, toolopts, utils


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


def mock_cli_arguments(args):
    """
    Return a list of cli arguments where the first one is always the name of
    the executable, followed by 'args'.
    """
    return sys.argv[0:1] + args


@pytest.fixture(autouse=True)
def apply_global_tool_opts(monkeypatch, global_tool_opts):
    monkeypatch.setattr(cli, "tool_opts", global_tool_opts)


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

    def test_cmdline_disablerepo_defaults_to_asterisk(self, monkeypatch):
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
    def test_bad_serverurl(self, caplog, monkeypatch, global_tool_opts, serverurl):
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

    def test_serverurl_with_no_rhsm(self, caplog, monkeypatch, global_tool_opts):
        monkeypatch.setattr(
            sys, "argv", mock_cli_arguments(["--serverurl", "localhost", "--no-rhsm", "--enablerepo", "testrepo"])
        )

        cli.CLI()

        message = "Ignoring the --serverurl option. It has no effect when --no-rhsm is used."
        assert message in caplog.text

    def test_serverurl_with_no_rhsm_credentials(self, caplog, monkeypatch, global_tool_opts):
        monkeypatch.setattr(sys, "argv", mock_cli_arguments(["--serverurl", "localhost"]))

        cli.CLI()

        message = (
            "Ignoring the --serverurl option. It has no effect when no credentials to"
            " subscribe the system were given."
        )
        assert message in caplog.text


@pytest.mark.parametrize(
    ("argv", "raise_exception", "no_rhsm_value"),
    (
        (mock_cli_arguments(["--no-rhsm"]), True, True),
        (mock_cli_arguments(["--no-rhsm", "--enablerepo", "test_repo"]), False, True),
    ),
)
@mock.patch("toolopts.tool_opts.no_rhsm", False)
@mock.patch("toolopts.tool_opts.enablerepo", [])
def test_no_rhsm_option_work(argv, raise_exception, no_rhsm_value, monkeypatch, caplog, global_tool_opts):
    monkeypatch.setattr(cli, "tool_opts", global_tool_opts)
    monkeypatch.setattr(sys, "argv", argv)

    if raise_exception:
        with pytest.raises(SystemExit):
            cli.CLI()
        assert "The --enablerepo option is required when --no-rhsm is used." in caplog.text
    else:
        cli.CLI()

    assert toolopts.tool_opts.no_rhsm == no_rhsm_value


@pytest.mark.parametrize(
    ("argv", "content", "output", "message"),
    (
        # pytest.param(
        #     mock_cli_arguments([]),
        #     """
        #     [subscription_manager]
        #     username=conf_user
        #     password=conf_pass
        #     activation_key=conf_key
        #     org=conf_org
        #     """,
        #     {"username": "conf_user", "password": "conf_pass", "activation_key": "conf_key", "org": "conf_org"},
        #     None,
        #     id="All values set in config",
        # ),
        # (
        #     mock_cli_arguments([]),
        #     """
        #     [subscription_manager]
        #     password=conf_pass
        #     """,
        #     {"password": "conf_pass"},
        #     None,
        # ),
        (
            mock_cli_arguments([]),
            """
            [subscription_manager]
            password = conf_pass
            [settings]
            incomplete_rollback = 1
            """,
            {"password": "conf_pass", "settings": "1"},
            None,
        ),
        # (
        #     mock_cli_arguments(["-p", "password"]),
        #     """
        #     [subscription_manager]
        #     activation_key=conf_key
        #     """,
        #     {"password": "password"},
        #     "You have passed either the RHSM password or activation key through both the command line and"
        #     " the configuration file. We're going to use the command line values.",
        # ),
        # (
        #     mock_cli_arguments(["-k", "activation_key", "-o", "org"]),
        #     """
        #     [subscription_manager]
        #     activation_key=conf_key
        #     """,
        #     {"activation_key": "activation_key"},
        #     "You have passed either the RHSM password or activation key through both the command line and"
        #     " the configuration file. We're going to use the command line values.",
        # ),
        # (
        #     mock_cli_arguments(["-k", "activation_key", "-o", "org"]),
        #     """
        #     [subscription_manager]
        #     password=conf_pass
        #     """,
        #     {"password": "conf_pass", "activation_key": "activation_key"},
        #     "You have passed either the RHSM password or activation key through both the command line and"
        #     " the configuration file. We're going to use the command line values.",
        # ),
        # (
        #     mock_cli_arguments(["-k", "activation_key", "-p", "password", "-o", "org"]),
        #     """
        #     [subscription_manager]
        #     password=conf_pass
        #     activation_key=conf_key
        #     """,
        #     {"password": "password", "activation_key": "activation_key"},
        #     "You have passed either the RHSM password or activation key through both the command line and"
        #     " the configuration file. We're going to use the command line values.",
        # ),
        # (
        #     mock_cli_arguments(["-o", "org"]),
        #     """
        #     [subscription_manager]
        #     password=conf_pass
        #     activation_key=conf_key
        #     """,
        #     {"password": "conf_pass", "activation_key": "conf_key"},
        #     "Either a password or an activation key can be used for system registration. We're going to use the"
        #     " activation key.",
        # ),
        # (
        #     mock_cli_arguments(["-u", "McLOVIN"]),
        #     """
        #     [subscription_manager]
        #     username=NotMcLOVIN
        #     """,
        #     {"username": "McLOVIN"},
        #     "You have passed the RHSM username through both the command line and"
        #     " the configuration file. We're going to use the command line values.",
        # ),
        # (
        #     mock_cli_arguments(["-o", "some-org"]),
        #     """
        #     [subscription_manager]
        #     org=a-different-org
        #     activation_key=conf_key
        #     """,
        #     {"org": "some-org"},
        #     "You have passed the RHSM org through both the command line and"
        #     " the configuration file. We're going to use the command line values.",
        # ),
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
    monkeypatch.setattr(cli, "CONFIG_PATHS", value=[path])
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
def test_multiple_auth_src_combined(argv, content, message, output, caplog, monkeypatch, tmpdir, global_tool_opts):
    """Test combination of password file or configuration file and CLI arguments."""
    path = os.path.join(str(tmpdir), "convert2rhel.file")
    with open(path, "w") as file:
        file.write(content)
    os.chmod(path, 0o600)
    # The path for file is the last argument
    argv.append(path)

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(cli, "CONFIG_PATHS", value=[""])
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


@pytest.mark.parametrize(
    ("content", "expected_message"),
    (
        (
            """
            [subscription_manager]
            incorect_option = yes
            """,
            "Unsupported option",
        ),
        (
            """
            [invalid_header]
            username = correct_username
            """,
            "Couldn't find header",
        ),
    ),
)
def test_options_from_config_files_invalid_head_and_options(content, expected_message, tmpdir, caplog):
    path = os.path.join(str(tmpdir), "convert2rhel.ini")

    with open(path, "w") as file:
        file.write(content)
    os.chmod(path, 0o600)

    opts = cli.options_from_config_files(path)

    assert expected_message in caplog.text


@pytest.mark.parametrize(
    ("content", "expected_message"),
    (
        (
            """
            [subscription_manager]
            """,
            "No options found for subscription_manager. It seems to be empty or commented.",
        ),
    ),
)
def test_options_from_config_files_commented_out_options(content, expected_message, tmpdir, caplog):
    path = os.path.join(str(tmpdir), "convert2rhel.ini")

    with open(path, "w") as file:
        file.write(content)
    os.chmod(path, 0o600)

    cli.options_from_config_files(path)
    assert expected_message in caplog.text


@pytest.mark.parametrize(
    ("content", "output"),
    (
        (
            """
            [subscription_manager]
            username = correct_username
            """,
            {"username": "correct_username"},
        ),
        # Test if we will unquote this correctly
        (
            """
            [subscription_manager]
            username = "correct_username"
            """,
            {"username": "correct_username"},
        ),
        (
            """
            [subscription_manager]
            password = correct_password
            """,
            {"password": "correct_password"},
        ),
        (
            """
            [subscription_manager]
            activation_key = correct_key
            password = correct_password
            username = correct_username
            org = correct_org
            """,
            {
                "username": "correct_username",
                "password": "correct_password",
                "activation_key": "correct_key",
                "org": "correct_org",
            },
        ),
        (
            """
            [subscription_manager]
            org = correct_org
            """,
            {"org": "correct_org"},
        ),
        (
            """
            [settings]
            incomplete_rollback = 1
            """,
            {"incomplete_rollback": "1"},
        ),
        (
            """
            [subscription_manager]
            org = correct_org

            [settings]
            incomplete_rollback = 1
            """,
            {"org": "correct_org", "incomplete_rollback": "1"},
        ),
        (
            """
            [settings]
            incomplete_rollback = 1
            tainted_kernel_module_check_skip = 1
            outdated_package_check_skip = 1
            allow_older_version = 1
            allow_unavailable_kmods = 1
            configure_host_metering = 1
            skip_kernel_currency_check = 1
            """,
            {
                "incomplete_rollback": "1",
                "tainted_kernel_module_check_skip": "1",
                "outdated_package_check_skip": "1",
                "allow_older_version": "1",
                "allow_unavailable_kmods": "1",
                "configure_host_metering": "1",
                "skip_kernel_currency_check": "1",
            },
        ),
    ),
)
def test_options_from_config_files_default(content, output, monkeypatch, tmpdir):
    """Test config files in default path."""
    path = os.path.join(str(tmpdir), "convert2rhel.ini")

    with open(path, "w") as file:
        file.write(content)
    os.chmod(path, 0o600)

    paths = ["/nonexisting/path", path]
    monkeypatch.setattr(cli, "CONFIG_PATHS", value=paths)
    opts = cli.options_from_config_files(None)

    for key in ["username", "password", "activation_key", "org"]:
        if key in opts:
            assert opts[key] == output[key]


@pytest.mark.parametrize(
    ("content", "output", "content_lower_priority"),
    (
        (
            """
            [subscription_manager]
            username = correct_username
            activation_key = correct_key
            """,
            {"username": "correct_username", "password": None, "activation_key": "correct_key", "org": None},
            """
            [subscription_manager]
            username = low_prior_username
            """,
        ),
        (
            """
            [subscription_manager]
            username = correct_username
            activation_key = correct_key
            """,
            {"username": "correct_username", "password": None, "activation_key": "correct_key", "org": None},
            """
            [subscription_manager]
            activation_key = low_prior_key
            """,
        ),
        (
            """
            [subscription_manager]
            activation_key = correct_key
            org = correct_org""",
            {"username": None, "password": None, "activation_key": "correct_key", "org": "correct_org"},
            """
            [subscription_manager]
            org = low_prior_org
            """,
        ),
        (
            """
            [subscription_manager]
            activation_key = correct_key
            Password = correct_password
            """,
            {"username": None, "password": "correct_password", "activation_key": "correct_key", "org": None},
            """
            [subscription_manager]
            password = low_prior_pass
            """,
        ),
        (
            """
            [subscription_manager]
            activation_key = correct_key
            Password = correct_password
            """,
            {"username": None, "password": "correct_password", "activation_key": "correct_key", "org": None},
            """
            [INVALID_HEADER]
            password = low_prior_pass
            """,
        ),
        (
            """
            [subscription_manager]
            activation_key = correct_key
            Password = correct_password
            """,
            {"username": None, "password": "correct_password", "activation_key": "correct_key", "org": None},
            """
            [subscription_manager]
            incorrect_option = incorrect_option
            """,
        ),
    ),
)
def test_options_from_config_files_specified(content, output, content_lower_priority, monkeypatch, tmpdir, caplog):
    """Test user specified path for config file."""
    path_higher_priority = os.path.join(str(tmpdir), "convert2rhel.ini")
    with open(path_higher_priority, "w") as file:
        file.write(content)
    os.chmod(path_higher_priority, 0o600)

    path_lower_priority = os.path.join(str(tmpdir), "convert2rhel_lower.ini")
    with open(path_lower_priority, "w") as file:
        file.write(content_lower_priority)
    os.chmod(path_lower_priority, 0o600)

    paths = [path_higher_priority, path_lower_priority]
    monkeypatch.setattr(cli, "CONFIG_PATHS", value=paths)

    opts = cli.options_from_config_files(None)

    for key in ["username", "password", "activation_key", "org"]:
        if key in opts:
            assert opts[key] == output[key]


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
        cli._validate_serverurl_parsing(url_parts)


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
        # The message is a log of used command
        (mock_cli_arguments(["-o", "org", "-k", "key"]), "-o ***** -k *****"),
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

    assert message in caplog.text


@pytest.mark.parametrize(
    ("argv", "expected"),
    (
        (mock_cli_arguments(["convert"]), "conversion"),
        (mock_cli_arguments(["analyze"]), "analysis"),
        (mock_cli_arguments([]), "conversion"),
    ),
)
def test_pre_assessment_set(argv, expected, monkeypatch):
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
    t_opts = toolopts.ToolOpts()
    t_opts.username = username
    t_opts.password = password
    t_opts.org = organization
    t_opts.activation_key = activation_key
    t_opts.no_rhsm = no_rhsm

    assert cli._should_subscribe(t_opts) is expected


@pytest.mark.parametrize(
    ("argv", "env_var", "expected", "message"),
    (
        (
            ["analyze", "--no-rpm-va"],
            False,
            False,
            "We will proceed with ignoring the --no-rpm-va option as running rpm -Va in the analysis mode is essential for a complete rollback to the original system state at the end of the analysis.",
        ),
        (
            ["analyze", "--no-rpm-va"],
            True,
            False,
            "We will proceed with ignoring the --no-rpm-va option as running rpm -Va in the analysis mode is essential for a complete rollback to the original system state at the end of the analysis.",
        ),
        (
            ["--no-rpm-va"],
            False,
            False,
            "We need to run the 'rpm -Va' command to be able to perform a complete rollback of changes done to the system during the pre-conversion analysis. If you accept the risk of an incomplete rollback, set the CONVERT2RHEL_INCOMPLETE_ROLLBACK=1 environment variable. Otherwise, remove the --no-rpm-va option.",
        ),
        (["--no-rpm-va"], True, True, ""),
    ),
)
def test_setting_no_rpm_va(argv, env_var, expected, message, monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", mock_cli_arguments(argv))
    if env_var:
        monkeypatch.setenv("CONVERT2RHEL_INCOMPLETE_ROLLBACK", "1")

    try:
        cli.CLI()
    except SystemExit:
        pass

    assert cli.tool_opts.no_rpm_va == expected
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
        ("activation_key", "org", []),
        ("activation_key", "org", ["analyze", "-u name", "-p pass"]),
        (None, None, ["analyze", "-u name", "-p pass"]),
    ),
)
def test_cli_args_config_file_cornercase(activation_key, organization, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", mock_cli_arguments(argv))
    t_opts = toolopts.ToolOpts()
    t_opts.org = organization
    t_opts.activation_key = activation_key
    t_opts.no_rhsm = True
    monkeypatch.setattr(toolopts, "tool_opts", t_opts)

    # Make sure it doesn't raise an exception
    cli.CLI()
