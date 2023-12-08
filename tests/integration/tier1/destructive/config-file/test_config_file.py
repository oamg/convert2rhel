import os

from collections import namedtuple

from envparse import env


Config = namedtuple("Config", "path content")


def create_files(config):
    for cfg in config:
        with open(os.path.expanduser(cfg.path), mode="w") as handler:
            handler.write(cfg.content)

        os.chmod(os.path.expanduser(cfg.path), 0o600)


def remove_files(config):
    for cfg in config:
        os.remove(os.path.expanduser(cfg.path))


def test_conversion(convert2rhel):
    activation_key = "[subscription_manager]\nactivation_key = {}\norg = {}".format(
        env.str("RHSM_KEY"), env.str("RHSM_ORG")
    )
    config = [Config("~/.convert2rhel.ini", activation_key)]
    create_files(config)

    with convert2rhel("-y --serverurl {} --debug".format(env.str("RHSM_SERVER_URL"))) as c2r:
        c2r.expect("DEBUG - Found activation_key in /root/.convert2rhel.ini")
        c2r.expect("DEBUG - Found org in /root/.convert2rhel.ini")
        c2r.expect("Conversion successful!")

    assert c2r.exitstatus == 0
