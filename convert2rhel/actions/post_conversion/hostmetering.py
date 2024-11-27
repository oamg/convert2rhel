# Copyright(C) 2024 Red Hat, Inc.
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

from convert2rhel import actions, systeminfo
from convert2rhel.logger import root_logger
from convert2rhel.pkgmanager import call_yum_cmd
from convert2rhel.subscription import get_rhsm_facts
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import run_subprocess, warn_deprecated_env


logger = root_logger.getChild(__name__)


class ConfigureHostMetering(actions.Action):
    """Configure host metering on a machine if it's needed."""

    id = "CONFIGURE_HOST_METERING_IF_NEEDED"

    def run(self):
        """
        Decide whether to install, enable and start host-metering on the system based on the setting of
        'configure_host_metering' in /etc/convert2rhel.ini.

        The behavior can be controlled via the 'configure_host_metering' as follows:
        - "auto": host-metering will be configured based on the above conditions
        - "force": forces configuration of host-metering (e.g., even if not running on a hyperscaler)
        - any other value: Will be ignored and host metering will not be configured.
        :return: True if host-metering is configured successfully, False otherwise.
        :rtype: bool
        """
        logger.task("Configure host-metering")

        super(ConfigureHostMetering, self).run()

        warn_deprecated_env("CONVERT2RHEL_CONFIGURE_HOST_METERING")
        if not self._check_host_metering_configuration():
            return False

        if system_info.version.major != 7 and tool_opts.configure_host_metering == "auto":
            logger.info("Did not perform host metering configuration. Only supported for RHEL 7.")
            self.add_message(
                level="INFO",
                id="CONFIGURE_HOST_METERING_SKIP",
                title="Did not perform host metering configuration.",
                description="Host metering is supportted only for RHEL 7.",
            )
            return False

        is_hyperscaler = self.is_running_on_hyperscaler()

        if not is_hyperscaler and tool_opts.configure_host_metering == "auto":
            logger.info("Did not perform host-metering configuration.")
            self.add_message(
                level="INFO",
                id="CONFIGURE_HOST_METERING_SKIP",
                title="Did not perform host metering configuration as not needed.",
                description="Host metering is not needed on the system.",
            )
            return False

        logger.info("Installing host-metering packages.")
        output, ret_install = call_yum_cmd("install", ["host-metering"])
        if ret_install:
            logger.warning("Failed to install host-metering rpms.")
            self.add_message(
                level="WARNING",
                id="INSTALL_HOST_METERING_FAILURE",
                title="Failed to install host metering package.",
                description="When installing host metering package an error occurred meaning we can't"
                " enable host metering on the system.",
                diagnosis="`yum install host-metering` command returned {ret_install} with message {output}".format(
                    ret_install=ret_install, output=output
                ),
                remediations="You can try install and set up the host metering"
                " manually using following commands:\n"
                " - `yum install host-metering`\n"
                " - `systemctl enable host-metering.service`\n"
                " - `systemctl start host-metering.service`",
            )
            return False

        command, error_message = self._enable_host_metering_service()
        # If there is any failure, the failed command would be present
        if any(command):
            self.add_message(
                level="WARNING",
                id="CONFIGURE_HOST_METERING_FAILURE",
                title="Failed to enable and start host metering service.",
                description="The host metering service failed to start"
                " successfully and won't be able to keep track.",
                diagnosis="Command {command} failed with {error_message}".format(
                    command=command, error_message=error_message
                ),
                remediations="You can try set up the host metering"
                " service manually using following commands:\n"
                " - `systemctl enable host-metering.service`\n"
                " - `systemctl start host-metering.service`",
            )
            return False

        service_running = systeminfo.is_systemd_managed_service_running("host-metering.service")

        if not service_running:
            logger.critical_no_exit("host-metering service is not running.")
            self.set_result(
                level="ERROR",
                id="HOST_METERING_NOT_RUNNING",
                title="Host metering service is not running.",
                description="host-metering.service is not running.",
                remediations="You can try to start the service manually"
                " by running following command:\n"
                " - `systemctl start host-metering.service`",
            )

        return service_running

    def _check_host_metering_configuration(self):
        """Check if host metering has been configured by the user and if the configuration option has the right value.
        If the value is auto|force, the host metering should be configured on the system.

        :return: Return True if the value is equal to auto|force, otherwise False
        :rtype: bool
        """
        if tool_opts.configure_host_metering is None:
            logger.debug("Configuration of host metering has not been enabled. Skipping it.")
            self.add_message(
                level="INFO",
                id="CONFIGURE_HOST_METERING_SKIP",
                title="Did not perform host metering configuration.",
                description="Configuration of host metering has been skipped.",
                diagnosis="We haven't detected 'configure_host_metering' in the convert2rhel.ini config file nor"
                " the CONVERT2RHEL_CONFIGURE_HOST_METERING environment variable.",
            )
            return False

        if tool_opts.configure_host_metering not in ("force", "auto"):
            logger.debug(
                "Unexpected value of 'configure_host_metering' in convert2rhel.ini or the"
                " CONVERT2RHEL_CONFIGURE_HOST_METERING environment variable: {}".format(
                    tool_opts.configure_host_metering
                )
            )
            self.add_message(
                level="WARNING",
                id="UNRECOGNIZED_OPTION_CONFIGURE_HOST_METERING",
                title="Unexpected value of the host metering setting",
                diagnosis="Unexpected value of 'configure_host_metering' in convert2rhel.ini or the"
                " CONVERT2RHEL_CONFIGURE_HOST_METERING environment variable: {}".format(
                    tool_opts.configure_host_metering
                ),
                description="Host metering will not be configured.",
                remediations="Set the option to 'auto' or 'force' if you want to configure host metering.",
            )
            return False

        if tool_opts.configure_host_metering == "force":
            logger.warning(
                "You've set the host metering setting to 'force'."
                " Please note that this option is mainly used for testing and will configure host-metering unconditionally. "
                " For generic usage please use the 'auto' option."
            )
            self.add_message(
                level="WARNING",
                id="FORCED_CONFIGURE_HOST_METERING",
                title="Configuration of host metering set to 'force'",
                description="Please note that this option is mainly used for testing and"
                " will configure host-metering unconditionally."
                " For generic usage please use the 'auto' option.",
            )
        elif tool_opts.configure_host_metering == "auto":
            logger.debug("Automatic detection of host hyperscaler and configuration.")

        return True

    def is_running_on_hyperscaler(self):
        """
        Check if the system is running on hyperscaler. Currently supported
        hyperscalers are aws, azure and gcp.

        :param rhsm_facts: Facts about the system from RHSM.
        :type rhsm_facts: dict
        :return: True if the system is running on hyperscaler, False otherwise.
        :rtype: bool
        """
        rhsm_facts = get_rhsm_facts()

        is_aws = rhsm_facts.get("aws_instance_id")
        is_azure = rhsm_facts.get("azure_instance_id")
        is_gcp = rhsm_facts.get("gcp_instance_id")
        return any([is_aws, is_azure, is_gcp])

    def _enable_host_metering_service(self):
        """
        Enables and starts the host metering service.
        Return command and it's output in case of fail.

        Example:
            Command called: systemctl enable host-metering.service
            Return values:
                (command, message)
                command = "systemctl enable host-metering.service"
                message = "Some message with error description."

        :return: Empty string if host-metering is enabled and started successfully. Otherwise failed command and it's output if available.
        :rtype: tuple(str, str)
        """

        logger.info("Enabling host-metering service.")
        command = ["systemctl", "enable", "host-metering.service"]
        output, ret_enable = run_subprocess(command)
        if output:
            logger.debug("Output of systemctl call: {}".format(output))
        if ret_enable:
            logger.warning("Failed to enable host-metering service.")
            return " ".join(command), output

        logger.info("Starting host-metering service.")
        command = ["systemctl", "start", "host-metering.service"]
        output, ret_start = run_subprocess(command)
        if output:
            logger.debug("Output of systemctl call: {}".format(output))
        if ret_start:
            logger.warning("Failed to start host-metering service.")
            return " ".join(command), output

        # All commands succeeded, no error output found
        return "", ""
