import os

from collections import namedtuple

import pytest


Config = namedtuple("Config", "path content")


def create_files(config):
    for cfg in config:
        with open(os.path.expanduser(cfg.path), "w") as f:
            f.write(cfg.content)

        os.chmod(os.path.expanduser(cfg.path), 0o600)


def remove_files(config):
    for cfg in config:
        os.remove(os.path.expanduser(cfg.path))


@pytest.mark.test_config_custom_path_custom_filename
def test_user_path_custom_filename(convert2rhel):
    config = [Config("~/.convert2rhel_custom.ini", "[subscription_manager]\nactivation_key = config_activationkey")]
    create_files(config)

    with convert2rhel('--no-rpm-va --debug -c "~/.convert2rhel_custom.ini"') as c2r:
        if c2r.expect("DEBUG - Found activation_key in /root/.convert2rhel_custom.ini") == 0:
            c2r.sendcontrol("c")
    assert c2r.exitstatus != 0

    remove_files(config)


@pytest.mark.test_config_custom_path_standard_filename
def test_user_path_std_filename(convert2rhel):
    config = [Config("~/.convert2rhel.ini", "[subscription_manager]\npassword = config_password")]
    create_files(config)

    with convert2rhel("--no-rpm-va --debug") as c2r:
        if c2r.expect("DEBUG - Found password in /root/.convert2rhel.ini") == 0:
            c2r.sendcontrol("c")
    assert c2r.exitstatus != 0

    remove_files(config)


@pytest.mark.test_config_cli_priority
def test_user_path_cli_priority(convert2rhel):
    config = [
        Config(
            "~/.convert2rhel.ini",
            "[subscription_manager]\nusername = config_username\npassword = config_password\nacitvation_key = config_key\norg = config_org",
        )
    ]
    create_files(config)

    with convert2rhel("--no-rpm-va --password password --debug") as c2r:
        # Found options in config file
        c2r.expect("DEBUG - Found username in /root/.convert2rhel.ini")
        c2r.expect("DEBUG - Found password in /root/.convert2rhel.ini")
        c2r.expect("DEBUG - Found activation_key in /root/.convert2rhel.ini")
        c2r.expect("DEBUG - Found org in /root/.convert2rhel.ini")

        c2r.expect(
            "WARNING - You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values."
        )
        if (
            c2r.expect(
                "WARNING - You have passed either the RHSM username or org through both the command line and"
                " the configuration file. We're going to use the command line values."
            )
            == 0
        ):
            c2r.sendcontrol("c")
    assert c2r.exitstatus != 0

    remove_files(config)


@pytest.mark.test_config_password_file_priority
def test_user_path_pswd_file_priority(convert2rhel):
    config = [
        Config("~/.convert2rhel.ini", "[subscription_manager]\npassword = config_password"),
        Config("~/password_file", "file_password"),
    ]
    create_files(config)

    with convert2rhel('--no-rpm-va -f "~/password_file" --debug') as c2r:
        c2r.expect("DEBUG - Found password in /root/.convert2rhel.ini")
        c2r.expect("WARNING - Deprecated. Use -c | --config-file instead.")
        if (
            c2r.expect(
                "WARNING - You have passed the RHSM credentials both through a config file and through a password file."
                " We're going to use the password file."
            )
            == 0
        ):
            c2r.sendcontrol("c")
    assert c2r.exitstatus != 0

    remove_files(config)


@pytest.mark.test_config_standard_paths_priority_diff_methods
def test_std_paths_priority_diff_methods(convert2rhel):
    config = [
        Config("~/.convert2rhel.ini", "[subscription_manager]\npassword = config_password"),
        Config("/etc/convert2rhel.ini", "[subscription_manager]\nactivation_key = config2_activationkey"),
    ]
    create_files(config)

    with convert2rhel("--no-rpm-va --debug") as c2r:
        c2r.expect("DEBUG - Found password in /root/.convert2rhel.ini")
        c2r.expect("DEBUG - Found activation_key in /etc/convert2rhel.ini")
        c2r.expect(
            "WARNING - Passing the RHSM password or activation key through the --activationkey or --password options"
            " is insecure as it leaks the values through the list of running processes."
            " We recommend using the safer --config-file option instead."
        )
        if (
            c2r.expect(
                "WARNING - Either a password or an activation key can be used for system registration."
                " We're going to use the activation key."
            )
            == 0
        ):
            c2r.sendcontrol("c")
    assert c2r.exitstatus != 0

    remove_files(config)


@pytest.mark.test_config_standard_paths_priority
def test_std_paths_priority(convert2rhel):
    config = [
        Config("~/.convert2rhel.ini", "[subscription_manager]\npassword = config_password"),
        Config("/etc/convert2rhel.ini", "[subscription_manager]\npassword = config_password"),
    ]
    create_files(config)

    with convert2rhel("--no-rpm-va --debug") as c2r:
        if c2r.expect("DEBUG - Found password in /root/.convert2rhel.ini") == 0:
            c2r.sendcontrol("c")
    assert c2r.exitstatus != 0

    remove_files(config)
