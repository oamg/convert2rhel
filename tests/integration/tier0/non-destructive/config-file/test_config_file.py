import os

from collections import namedtuple

from conftest import TEST_VARS


Config = namedtuple("Config", "path content")


def create_files(config):
    for cfg in config:
        with open(os.path.expanduser(cfg.path), "w") as f:
            f.write(cfg.content)

        os.chmod(os.path.expanduser(cfg.path), 0o600)


def remove_files(config):
    for cfg in config:
        os.remove(os.path.expanduser(cfg.path))


def test_std_path_std_filename(convert2rhel):
    """
    Verify that the standard path to the config file is accepted,
    with the config file having standard filename.
    """
    config = [
        Config(
            "~/.convert2rhel.ini",
            # We disable the Black pre-commit hook because it changes formatting
            # of the following configuration files, which makes them hard to read.
            # https://black.readthedocs.io/en/stable/usage_and_configuration/the_basics.html#ignoring-sections
            # fmt: off
            (
                "[subscription_manager]\n"
                "password = config_password\n"
            ),
            # fmt: on
        )
    ]
    create_files(config)

    with convert2rhel("--debug") as c2r:
        c2r.expect("DEBUG - Found password in /root/.convert2rhel.ini")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus == 1

    remove_files(config)


def test_user_path_custom_filename(convert2rhel):
    """
    Verify that both custom path and custom filename are accepted.
    The config file is created at a custom path with a custom
    filename and the path is passed to the utility command.
    """
    config = [
        Config(
            "~/.convert2rhel_custom.ini",
            # fmt: off
            (
                "[subscription_manager]\n"
                "activation_key = config_activationkey\n"
            ),
            # fmt: on
        )
    ]
    create_files(config)

    with convert2rhel('--debug -c "~/.convert2rhel_custom.ini"') as c2r:
        c2r.expect("DEBUG - Found activation_key in /root/.convert2rhel_custom.ini")

    assert c2r.exitstatus == 1

    remove_files(config)


def test_config_cli_priority(convert2rhel):
    """
    Verify that the values provided to the CLI command are preferred
    to those provided in the config file.
    """
    config = [
        Config(
            "~/.convert2rhel.ini",
            # fmt: off
            (
                "[subscription_manager]\n"
                "username = config_username\n"
                "password = config_password\n"
                "activation_key = config_key\n"
                "org = config_org\n"
            ),
            # fmt: on
        )
    ]
    create_files(config)

    with convert2rhel("--username username --password password --debug") as c2r:
        # Found options in config file
        c2r.expect("DEBUG - Found username in /root/.convert2rhel.ini", timeout=120)
        c2r.expect("DEBUG - Found password in /root/.convert2rhel.ini", timeout=120)
        c2r.expect("DEBUG - Found activation_key in /root/.convert2rhel.ini", timeout=120)
        c2r.expect("DEBUG - Found org in /root/.convert2rhel.ini", timeout=120)
        c2r.expect(
            "WARNING - You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values.",
            timeout=120,
        )
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus == 1

    remove_files(config)


def test_config_standard_paths_priority_diff_methods(convert2rhel, shell):
    """
    Verify that with multiple config files each providing different method
    (password and activation key) the activation key is preferred.
    """
    config = [
        Config(
            "~/.convert2rhel.ini",
            # fmt: off
            (
                "[subscription_manager]\n"
                "password   = config_password\n"
                "username   = config_username\n"
            ),
            # fmt: on
        ),
        Config(
            "/etc/convert2rhel.ini",
            # fmt: off
            (
                "[subscription_manager]\n"
                f"activation_key    = {TEST_VARS['RHSM_SCA_KEY']}\n"
                f"org               = {TEST_VARS['RHSM_SCA_ORG']}\n"
            ),
            # fmt: on
        ),
    ]
    create_files(config)

    # shell("cat ~/.convert2rhel.ini")
    shell("cat /etc/convert2rhel.ini")

    with convert2rhel(f"analyze --serverurl {TEST_VARS['RHSM_SERVER_URL']} -y --debug") as c2r:
        c2r.expect("DEBUG - Found password in /root/.convert2rhel.ini")
        c2r.expect("DEBUG - Found activation_key in /etc/convert2rhel.ini")
        c2r.expect(
            "WARNING - Passing the RHSM password or activation key through the --activationkey or --password options"
            " is insecure as it leaks the values through the list of running processes."
            " We recommend using the safer --config-file option instead."
        )

        c2r.expect(
            "WARNING - Either a password or an activation key can be used for system registration."
            " We're going to use the activation key."
        )
        c2r.expect("SUBSCRIBE_SYSTEM has succeeded")

    assert c2r.exitstatus == 0

    remove_files(config)


def test_config_standard_paths_priority(convert2rhel):
    """
    Verify priorities of standard config file paths.
    Config file located in the home folder to be preferred.
    """
    config = [
        Config(
            "~/.convert2rhel.ini",
            # fmt: off
            (
                "[subscription_manager]\n"
                f"username = {TEST_VARS['RHSM_SCA_USERNAME']}\n"
                f"password = {TEST_VARS['RHSM_SCA_PASSWORD']}\n"
            ),
            # fmt: on
        ),
        Config(
            "/etc/convert2rhel.ini",
            # fmt: off
            (
                "[subscription_manager]\n"
                "username = config_username\n"
                "password = config_password\n"
            ),
            # fmt: on
        ),
    ]
    create_files(config)

    with convert2rhel(f"analyze --serverurl {TEST_VARS['RHSM_SERVER_URL']} -y --debug") as c2r:
        c2r.expect("DEBUG - Found username in /root/.convert2rhel.ini")
        c2r.expect("DEBUG - Found password in /root/.convert2rhel.ini")
        c2r.expect("SUBSCRIBE_SYSTEM has succeeded")

    assert c2r.exitstatus == 0

    remove_files(config)
