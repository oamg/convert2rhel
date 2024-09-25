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

import logging
import os

from convert2rhel.utils.subscription import setup_rhsm_parts


loggerinst = logging.getLogger(__name__)


class ToolOpts:
    def _handle_config_conflict(self, config_sources):
        file_config = next((config for config in config_sources if config.SOURCE == "configuration file"), None)
        # No file config detected, let's just bail out.
        if not file_config:
            return

        cli_config = next(config for config in config_sources if config.SOURCE == "command line")

        # Config files matches
        if file_config.username and cli_config.username:
            loggerinst.warning(
                "You have passed the RHSM username through both the command line and the"
                " configuration file. We're going to use the command line values."
            )
            self.username = cli_config.username

        if file_config.org and cli_config.org:
            loggerinst.warning(
                "You have passed the RHSM org through both the command line and the"
                " configuration file. We're going to use the command line values."
            )
            self.org = cli_config.org

        if file_config.activation_key and cli_config.activation_key:
            loggerinst.warning(
                "You have passed the RHSM activation key through both the command line and the"
                " configuration file. We're going to use the command line values."
            )
            self.activation_key = cli_config.activation_key

        if file_config.password and cli_config.password:
            loggerinst.warning(
                "You have passed the RHSM password through both the command line and the"
                " configuration file. We're going to use the command line values."
            )
            self.password = cli_config.password

        if (cli_config.password or file_config.password) and not (cli_config.username or file_config.username):
            loggerinst.warning(
                "You have passed the RHSM password without an associated username. Please provide a username together"
                " with the password."
            )

        if (cli_config.username or file_config.username) and not (cli_config.password or file_config.password):
            loggerinst.warning(
                "You have passed the RHSM username without an associated password. Please provide a password together"
                " with the username."
            )

        if self.password and self.activation_key:
            loggerinst.warning(
                "Either a password or an activation key can be used for system registration."
                " We're going to use the activation key."
            )

        # Corner cases
        if file_config.activation_key and cli_config.password:
            loggerinst.warning(
                "You have passed either the RHSM password or activation key through both the command line and"
                " the configuration file. We're going to use the command line values."
            )
            self.activation_key = None
            self.org = None

        if self.no_rpm_va and self.activity != "analysis":
            # If the incomplete_rollback option is not set in the config file, we will raise a SystemExit through
            # logger.critical, otherwise, just set the no_rpm_va to False and move on.
            if not file_config.incomplete_rollback:
                message = (
                    "We need to run the 'rpm -Va' command to be able to perform a complete rollback of changes"
                    " done to the system during the pre-conversion analysis. If you accept the risk of an"
                    " incomplete rollback, set the CONVERT2RHEL_INCOMPLETE_ROLLBACK=1 environment"
                    " variable. Otherwise, remove the --no-rpm-va option."
                )
                loggerinst.critical(message)

    def _handle_missing_options(self):
        if (self.org and not self.activation_key) or (not self.org and self.activation_key):
            loggerinst.critical(
                "Either the --org or the --activationkey option is missing. You can't use one without the other."
            )

    def set_opts(self, key, value):
        if not hasattr(self, key):
            setattr(self, key, value)
            return

        current_attribute_value = getattr(self, key)

        if value and not current_attribute_value:
            setattr(self, key, value)

    def update_opts(self, key, value):
        """Update a given option in toolopts.

        :param key:
        :type key: str
        :param value:
        :type value: str
        """
        if key and value:
            setattr(self, key, value)

    def _handle_rhsm_parts(self):
        # Sending itself as the ToolOpts class contains all the attribute references.
        rhsm_parts = setup_rhsm_parts(self)

        for key, value in rhsm_parts.items():
            self.set_opts(key, value)

    def initialize(self, config_sources):
        # Populate the values for each config class before applying the attribute to the class.
        [config.run() for config in config_sources]

        # Apply the attributes from config classes to ToolOpts.
        for config in config_sources:
            [self.set_opts(key, value) for key, value in vars(config).items()]

        # This is being handled here because we have conditions inside the `setup_rhsm_parts` that checks for
        # username/password, and since that type of information can come from CLI or Config file, we are putting it
        # here.
        self._handle_rhsm_parts()

        # Handle the conflicts between FileConfig and other Config classes
        self._handle_config_conflict(config_sources)

        # Handle critical conflicts before finalizing
        self._handle_missing_options()


tool_opts = ToolOpts()
