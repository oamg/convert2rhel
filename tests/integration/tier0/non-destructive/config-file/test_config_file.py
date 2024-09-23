import os
import shutil

from collections import namedtuple

import pytest

from conftest import TEST_VARS


Config = namedtuple("Config", "path content")


@pytest.fixture(scope="function")
def c2r_config_setup(request, backup_directory):
    """
    Fixture that set up the config files passed as parameter.
    """
    # Get list of configs
    configs = request.param
    if not isinstance(configs, list):
        configs = [configs]

    # Original convert2rhel config that is installed by default by c2r
    c2r_original_config = "/etc/convert2rhel.ini"

    bkp_original_config = shutil.copy2(c2r_original_config, backup_directory)
    for cfg in configs:
        with open(os.path.expanduser(cfg.path), "w") as f:
            f.write(cfg.content)

        os.chmod(os.path.expanduser(cfg.path), 0o600)

    yield

    for cfg in configs:
        os.remove(os.path.expanduser(cfg.path))

    shutil.move(bkp_original_config, c2r_original_config)


# We disable formatting because it changes the configuration
# files in parametrize, which makes them hard to read.
# https://docs.astral.sh/ruff/formatter/#format-suppression
# fmt: off
@pytest.mark.parametrize(
    "c2r_config_setup",
    [
        Config(
            "~/.convert2rhel.ini",
            (
                "[subscription_manager]\n"
                "password = config_password\n"
            ),
        )
    ],
    indirect=True,
)
def test_std_path_std_filename(convert2rhel, c2r_config_setup):
    """
    Verify that the standard path to the config file is accepted,
    with the config file having standard filename.
    """
    with convert2rhel("--debug") as c2r:
        c2r.expect("DEBUG - Found password in subscription_manager")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus == 1


@pytest.mark.parametrize(
    "c2r_config_setup",
    [
        Config(
            "~/.convert2rhel_custom.ini",
            (
                "[subscription_manager]\n"
                "activation_key = config_activationkey\n"
            ),
        )
    ],
    indirect=True,
)
def test_user_path_custom_filename(convert2rhel, c2r_config_setup):
    """
    Verify that both custom path and custom filename are accepted.
    The config file is created at a custom path with a custom
    filename and the path is passed to the utility command.
    """
    with convert2rhel('--debug -c "~/.convert2rhel_custom.ini"') as c2r:
        c2r.expect("DEBUG - Checking configuration file at /root/.convert2rhel_custom.ini")
        c2r.expect("DEBUG - Found activation_key in subscription_manager")

    assert c2r.exitstatus == 1


@pytest.mark.parametrize(
    "c2r_config_setup",
    [
        Config(
            "~/.convert2rhel.ini",
            (
                "[subscription_manager]\n"
                "username = config_username\n"
                "password = config_password\n"
                "activation_key = config_key\n"
                "org = config_org\n"
            ),
        )
    ],
    indirect=True,
)
def test_config_cli_priority(convert2rhel, c2r_config_setup):
    """
    Verify that the values provided to the CLI command are preferred
    to those provided in the config file.
    """
    with convert2rhel("--username username --password password --debug") as c2r:
        # Found options in config file
        c2r.expect("DEBUG - Checking configuration file at /root/.convert2rhel.ini", timeout=120)
        c2r.expect("DEBUG - Found username in subscription_manager", timeout=120)
        c2r.expect("DEBUG - Found password in subscription_manager", timeout=120)
        c2r.expect("DEBUG - Found activation_key in subscription_manager", timeout=120)
        c2r.expect("DEBUG - Found org in subscription_manager", timeout=120)
        c2r.expect(
            "WARNING - You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values.",
            timeout=120,
        )
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus == 1


@pytest.mark.parametrize(
    "c2r_config_setup",
    [
        [
            Config(
                "~/.convert2rhel.ini",
                (
                    "[subscription_manager]\n"
                    "password   = config_password\n"
                    "username   = config_username\n"
                ),
            ),
            Config(
                "/etc/convert2rhel.ini",
                (
                    "[subscription_manager]\n"
                    f"activation_key    = {TEST_VARS['RHSM_SCA_KEY']}\n"
                    f"org               = {TEST_VARS['RHSM_SCA_ORG']}\n"
                ),
            ),
        ]
    ],
    indirect=True,
)
def test_config_standard_paths_priority_diff_methods(convert2rhel, c2r_config_setup):
    """
    Verify that with multiple config files each providing different method
    (password and activation key) the activation key is preferred.
    """
    with convert2rhel(f"analyze --serverurl {TEST_VARS['RHSM_SERVER_URL']} -y --debug") as c2r:
        c2r.expect("DEBUG - Checking configuration file at /etc/convert2rhel.ini", timeout=120)
        c2r.expect("DEBUG - Found activation_key in subscription_manager")
        c2r.expect("DEBUG - Found org in subscription_manager")
        c2r.expect("DEBUG - Checking configuration file at /root/.convert2rhel.ini", timeout=120)
        c2r.expect("DEBUG - Found password in subscription_manager")
        c2r.expect("DEBUG - Found username in subscription_manager")
        c2r.expect(
            "WARNING - Either a password or an activation key can be used for system registration."
            " We're going to use the activation key."
        )
        c2r.expect("SUBSCRIBE_SYSTEM has succeeded")

    assert c2r.exitstatus == 0


@pytest.mark.parametrize(
    "c2r_config_setup",
    [
        [
            Config(
                "~/.convert2rhel.ini",
                (
                    "[subscription_manager]\n"
                    f"username = {TEST_VARS['RHSM_SCA_USERNAME']}\n"
                    f"password = {TEST_VARS['RHSM_SCA_PASSWORD']}\n"
                ),
            ),
            Config(
                "/etc/convert2rhel.ini",
                (
                    "[subscription_manager]\n"
                    "username = config_username\n"
                    "password = config_password\n"
                ),
            ),
        ]
    ],
    indirect=True,
)
def test_config_standard_paths_priority(convert2rhel, c2r_config_setup):
    """
    Verify priorities of standard config file paths.
    Config file located in the home folder to be preferred.
    """
    with convert2rhel(f"analyze --serverurl {TEST_VARS['RHSM_SERVER_URL']} -y --debug") as c2r:
        c2r.expect("DEBUG - Found username in subscription_manager")
        c2r.expect("DEBUG - Found password in subscription_manager")
        c2r.expect("SUBSCRIBE_SYSTEM has succeeded")

    assert c2r.exitstatus == 0
