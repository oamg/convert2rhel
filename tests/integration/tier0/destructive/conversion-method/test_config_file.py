import os

from collections import namedtuple

from conftest import TEST_VARS


Config = namedtuple("Config", "path content")


def create_files(config):
    for cfg in config:
        with open(os.path.expanduser(cfg.path), mode="w") as handler:
            handler.write(cfg.content)

        os.chmod(os.path.expanduser(cfg.path), 0o600)


def remove_files(config):
    for cfg in config:
        os.remove(os.path.expanduser(cfg.path))


def test_conversion_with_config_file(convert2rhel):
    """
    Use config file to feed the credentials for the registration and verify a successful conversion.
    """
    activation_key = "[subscription_manager]\nactivation_key = {}\norg = {}".format(
        TEST_VARS["RHSM_SCA_KEY"], TEST_VARS["RHSM_SCA_ORG"]
    )
    config = [Config("~/.convert2rhel.ini", activation_key)]
    create_files(config)

    with convert2rhel("-y --serverurl {} --debug".format(TEST_VARS["RHSM_SERVER_URL"])) as c2r:
        c2r.expect("DEBUG - Found activation_key in subscription_manager")
        c2r.expect("DEBUG - Found org in subscription_manager")
        c2r.expect("Conversion successful!")

    assert c2r.exitstatus == 0
