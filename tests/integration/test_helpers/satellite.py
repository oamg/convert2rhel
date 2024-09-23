import pytest

from dotenv import dotenv_values
from test_helpers.common_functions import SystemInformationRelease
from test_helpers.shell import live_shell
from test_helpers.subscription_manager import SubscriptionManager
from test_helpers.vars import SYSTEM_RELEASE_ENV


class Satellite:
    def __init__(self, key=SYSTEM_RELEASE_ENV):
        self.shell = live_shell()
        # Key on which upon the command is selected
        self.key = key
        # File containing registration commands
        self._sat_reg_commands = dotenv_values("/var/tmp/.env_sat_reg")
        self._sat_script_location = "/var/tmp/register_to_satellite.sh"
        self.subman = SubscriptionManager()

    def get_satellite_curl_command(self):
        """
        Get the Satellite registration command for the respective system.
        """
        if not self._sat_reg_commands:
            pytest.fail(
                f"The {self._sat_reg_file} either not found or empty.\
                It is required for the satellite conversion to work."
            )

        return self._sat_reg_commands.get(self.key)

    def _curl_the_satellite_script(self, curl_command):
        assert (
            self.shell(f"{curl_command} -o {self._sat_script_location}", silent=True).returncode == 0
        ), "Failed to curl the satellite script to the machine."

        # [danmyway] This is just a mitigation of rhn-client-tools pkg obsoleting subscription-manager during upgrade
        # TODO remove when https://github.com/theforeman/foreman/pull/10280 gets merged and or foreman 3.12 is out
        # Should be around November 2024
        if "oracle-7.9" in SystemInformationRelease.system_release:
            self.shell(
                rf"sed -i 's/$PKG_MANAGER_UPGRADE subscription-manager/& --setopt=exclude=rhn-client-tools/' {self._sat_script_location}"
            )

    def _run_satellite_reg_script(self):
        assert (
            self.shell(f"chmod +x {self._sat_script_location} && /bin/bash {self._sat_script_location}").returncode == 0
        ), "Falied to run the satellite registration script."

    def register(self):
        curl_command = self.get_satellite_curl_command()

        # Subscription-manager is not in Oracle repositories so we have to add
        # our own client-tools-repo with subscription-manager package.
        if "oracle" in SYSTEM_RELEASE_ENV:
            self.subman.add_keys_and_certificates()
            self.subman.add_client_tools_repo()

        # Make sure it returned some value, otherwise it will fail.
        assert curl_command, "The registration command is empty."

        # Curl the Satellite registration script silently
        self._curl_the_satellite_script(curl_command)

        # Make the script executable and run the registration
        self._run_satellite_reg_script()

        ### This is a workaround which might be removed, when we enable the Satellite repositories by default
        repos_to_enable = self.shell(
            "subscription-manager repos --list | grep '^Repo ID:' | awk '{print $3}'"
        ).output.split()
        for repo in repos_to_enable:
            self.shell(f"subscription-manager repos --enable {repo}")

    def unregister(self):
        """
        Remove the subman packages installed by the registration script
        """
        self.subman.clean_up()
