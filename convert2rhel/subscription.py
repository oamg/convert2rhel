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

import hashlib
import json
import logging
import os
import re

from time import sleep

import dbus
import dbus.connection
import dbus.exceptions

from convert2rhel import backup, exceptions, i18n, pkghandler, repo, utils
from convert2rhel.backup.packages import RestorablePackageSet
from convert2rhel.redhatrelease import os_release_file
from convert2rhel.repo import DEFAULT_DNF_VARS_DIR, DEFAULT_YUM_VARS_DIR
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


loggerinst = logging.getLogger(__name__)

# We need to translate config settings between names used for the subscription-manager DBus API and
# names used for the RHSM config file.  This is the mapping for the settings we care about.
CONNECT_OPT_NAME_TO_CONFIG_KEY = {
    "host": "server.hostname",
    "port": "server.port",
    "handler": "server.prefix",
}

MAX_NUM_OF_ATTEMPTS_TO_SUBSCRIBE = 3
# Using a delay that could help when the RHSM/Satellite server is overloaded.
# The delay in seconds is a prime number that roughly doubles with each attempt.
REGISTRATION_ATTEMPT_DELAYS = [5, 11, 23]
# Seconds to wait for Registration to complete over DBus. If this timeout is exceeded, we retry.
REGISTRATION_TIMEOUT = 180

# Location of the RHSM generated facts json file.
RHSM_FACTS_FILE = "/var/lib/rhsm/facts/facts.json"

_CLIENT_TOOLS_REPOFILE_MAPPING = {
    7: "https://cdn-public.redhat.com/content/public/repofiles/client-tools-for-rhel-7-server.repo",
    8: "https://cdn-public.redhat.com/content/public/repofiles/client-tools-for-rhel-8.repo",
    9: "https://cdn-public.redhat.com/content/public/repofiles/client-tools-for-rhel-9.repo",
}

# Special case for RHEL 8.5 as we have to manually set the releasever to 8.5.
_CLIENT_TOOLS_RHEL_8_5_REPO = """\
[client-tools-for-rhel-8-rpms]
name=Red Hat Client Tools for RHEL 8
baseurl=https://cdn-public.redhat.com/content/public/addon/dist/client-tools8/8.5/$basearch/os/
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release
\n
"""


class UnregisterError(Exception):
    """Raised with problems unregistering a system."""


class SubscriptionRemovalError(Exception):
    """Raised when there is a failure in removing auto attached subscriptions"""


class RefreshSubscriptionManagerError(Exception):
    """Raised for problems telling subscription-manager to refresh the subscription information."""


class StopRhsmError(Exception):
    """Raised with problems stopping the rhsm daemon."""


class SubscriptionAutoAttachmentError(Exception):
    """Raised when there is a failure in auto attaching a subscription via subscription-manager."""


def remove_subscription():
    """Remove all subscriptions added from auto attachment"""
    loggerinst.info("Removing auto attached subscriptions.")
    subscription_removal_cmd = ["subscription-manager", "remove", "--all"]
    output, ret_code = utils.run_subprocess(subscription_removal_cmd, print_output=False)
    if ret_code != 0:
        raise SubscriptionRemovalError("Subscription removal result\n%s" % output)
    else:
        loggerinst.info("Subscription removal successful.")


def auto_attach_subscription():
    """
    Execute 'subscription-manager attach --auto' to auto attach a subscription. If it fails raise
    SubscriptionAutoAttachmentError.
    """
    _, ret_code = utils.run_subprocess(["subscription-manager", "attach", "--auto"])
    if ret_code != 0:
        raise SubscriptionAutoAttachmentError("Unsuccessful auto attachment of a subscription.")
    else:
        loggerinst.info("Subscription attachment successful.")

    return True


def unregister_system():
    """Unregister the system from RHSM."""
    loggerinst.info("Unregistering the system.")
    # We are calling run_subprocess with rpm here because of a bug in
    # Oracle/CentOS Linux 7 in which the process always exits with 1 in case of
    # a rollback when KeyboardInterrupt is raised.  To avoid many changes and
    # different conditionals to handle that, we are doing a simple call to rpm
    # to verify if subscription-manager is installed on the system.  This is
    # the current line in `rpm` that causes the process to exit with any
    # interaction with the yum library
    # https://github.com/rpm-software-management/rpm/blob/rpm-4.11.x/lib/rpmdb.c#L640
    _, ret_code = utils.run_subprocess(["rpm", "--quiet", "-q", "subscription-manager"])
    if ret_code != 0:
        loggerinst.info("The subscription-manager package is not installed.")
        return

    unregistration_cmd = ["subscription-manager", "unregister"]
    output, ret_code = utils.run_subprocess(unregistration_cmd, print_output=False)
    if ret_code != 0:
        raise UnregisterError("System unregistration result:\n%s" % output)
    else:
        loggerinst.info("System unregistered successfully.")


def register_system():
    """Register OS using subscription-manager."""

    # Loop the registration process until successful registration
    attempt = 0
    troublesome_exception = None
    while attempt < MAX_NUM_OF_ATTEMPTS_TO_SUBSCRIBE:
        attempt_msg = ""
        if attempt > 0:
            attempt_msg = "Attempt %d of %d: " % (
                attempt + 1,
                MAX_NUM_OF_ATTEMPTS_TO_SUBSCRIBE,
            )

        loggerinst.info(
            "%sRegistering the system using subscription-manager ...",
            attempt_msg,
        )

        # Force the system to be unregistered
        # The subscription-manager D-Bus API has a 'force' parameter, however
        # it is not implemented (and thus it does not work)
        # - in RHEL 7 and earlier
        # - in RHEL 8 before 8.8: https://bugzilla.redhat.com/show_bug.cgi?id=2118486
        # - in RHEL 9 before 9.2: https://bugzilla.redhat.com/show_bug.cgi?id=2121350
        # Explicitly unregister here to workaround that in any version,
        # to not have to do version checks, keeping things simpler.
        loggerinst.info("Unregistering the system to clear the server's state for our registration.")
        try:
            unregister_system()
        except UnregisterError as e:
            loggerinst.warning(str(e))

        # Hack: currently, on RHEL7, subscription-manager unregister is
        # reporting that the system is not registered but then calling the
        # subscription-manager Registration API reports that the system is
        # already registered. We suspect that the test host is being used for
        # a previous test.  In that test, the system is registered, then
        # rollback occurs which unregisters the server in some places but it
        # remains registered in other data.  Then registration fails.
        #
        # For the short term, we are going to stop the rhsm service to work
        # around this issue.  It should restart on its own when needed:
        loggerinst.info(
            "Stopping the RHSM service so that registration does not think that the host is already registered."
        )
        try:
            _stop_rhsm()
        except StopRhsmError as e:
            # The system really might not be registered yet and also not running rhsm
            # so ignore the error and try to register the system.
            loggerinst.info(str(e))

        # Register the system
        registration_cmd = RegistrationCommand.from_tool_opts(tool_opts)

        try:
            # Only in first attempt, in the next attempts the file is already restored from the first run
            if attempt <= 0:
                # The file /etc/os-release is needed for subscribing the system and is being removed with
                # <system-name>-release package in one of the steps before
                # RHELC-16
                os_release_file.restore(rollback=False)
        except (OSError, IOError) as e:
            loggerinst.critical_no_exit(
                "Failed to restore the /etc/os-release file needed for subscribing the system with message: %s" % str(e)
            )
            raise exceptions.CriticalError(
                id_="FAILED_TO_SUBSCRIBE_SYSTEM",
                title="Failed to subscribe system.",
                description="Failed to restore the /etc/os-release file needed for subscribing the system.",
                diagnosis="The restore failed with error %s." % (str(e)),
            )

        try:
            registration_cmd()
            # Need to remove the file, if it would stay there would be leftover /etc/os-release.rpmorig
            # after conversion
            # RHELC-16
            # Will be removed only if the registration succeed
            os_release_file.remove()
            loggerinst.info("System registration succeeded.")
        except KeyboardInterrupt:
            # When the user hits Control-C to exit, we shouldn't retry
            raise
        except Exception as e:
            loggerinst.info("System registration failed with error: %s" % str(e))
            troublesome_exception = e
            sleep(REGISTRATION_ATTEMPT_DELAYS[attempt])
            attempt += 1
            continue

        break

    else:  # While-else
        # We made the maximum number of subscription-manager retries and still failed
        loggerinst.critical_no_exit("Unable to register the system through subscription-manager.")
        raise exceptions.CriticalError(
            id_="FAILED_TO_SUBSCRIBE_SYSTEM",
            title="Failed to subscribe system.",
            description="After several attempts, convert2rhel was unable to subscribe the system using subscription-manager. This issue might occur because of but not limited to DBus, file permission-related issues, bad credentials, or network issues.",
            diagnosis="System registration failed with error %s." % (str(troublesome_exception)),
        )

    return None


def refresh_subscription_info():
    """
    Have subscription-manager pull new subscription data from the server.

    A byproduct of refreshing is that subscription-manager will reexamine the filesystem for the
    RHSM product certificate.  This is the reason that we need to call this function.
    """
    cmd = ["subscription-manager", "refresh"]
    output, ret_code = utils.run_subprocess(cmd, print_output=False)

    if ret_code != 0:
        raise RefreshSubscriptionManagerError(
            "Asking subscription-manager to reexamine its configuration failed: %s; output: %s" % (ret_code, output)
        )

    loggerinst.info("subscription-manager has reloaded its configuration.")


def _stop_rhsm():
    """Stop the rhsm service."""
    cmd = ["/bin/systemctl", "stop", "rhsm"]
    output, ret_code = utils.run_subprocess(cmd, print_output=False)
    if ret_code != 0:
        raise StopRhsmError("Stopping RHSM failed with code: %s; output: %s" % (ret_code, output))
    loggerinst.info("RHSM service stopped.")


class RegistrationCommand:
    def __init__(
        self,
        activation_key=None,
        org=None,
        username=None,
        password=None,
        rhsm_hostname=None,
        rhsm_port=None,
        rhsm_prefix=None,
    ):
        """
        A callable that can register a system with subscription-manager.

        :kwarg activation_key: subscription-manager activation_key that can be
            used to register the system. Org must be specified if this was given.
        :kwarg org: The organization that the activation_key is associated with.
            It is required if activation_key is specified.
        :kwarg username: Username to authenticate with subscription-manager.
            Required if password is specified.
        :kwarg password: Password to authenticate with subscription-manager.
            It is required if username is specified.
        :kwarg rhsm_hostname: Optional hostname of a subscription-manager backend.
            Useful when the customer has an on-prem subscription-manager instance.
        :kwarg rhsm_port: Optional port for a subscription-manager backend.
        :kwarg rhsm_prefix: Optional path element of a subscription-manager backend.

        .. note:: Either activation_key and org or username and password must
            be specified.
        """
        self.cmd = "subscription-manager"

        if activation_key and not org:
            raise ValueError("org must be specified if activation_key is used")

        self.activation_key = activation_key
        self.org = org

        self.password = password
        self.username = username

        if (password and not username) or (username and not password):
            raise ValueError("username and password must be used together")

        elif not password:
            # No password set
            if not self.activation_key:
                raise ValueError("activation_key and org or username and password must be specified")

        self.rhsm_hostname = rhsm_hostname
        self.rhsm_port = rhsm_port
        self.rhsm_prefix = rhsm_prefix

    @classmethod
    def from_tool_opts(cls, tool_opts):
        """
        Alternate constructor that gets subscription-manager args from ToolOpts.

        convert2rhel's command-line contains the information needed to register
        with subscription-manager. Get the information from the passed in
        ToolOpts structure to create the RegistrationCommand.

        :arg tool_opts: The :class:`convert2rhel.toolopts.ToolOpts` structure to
            retrieve the subscription-manager information from.
        """
        loggerinst.info("Gathering subscription-manager registration info ... ")

        registration_attributes = {}
        if tool_opts.org:
            loggerinst.info("    ... organization detected")
            registration_attributes["org"] = tool_opts.org

        if tool_opts.activation_key:
            # Activation key has been passed
            # -> username/password not required
            # -> organization required
            loggerinst.info("    ... activation key detected")
            registration_attributes["activation_key"] = tool_opts.activation_key

        else:
            # No activation key -> username/password required
            if tool_opts.username and tool_opts.password:
                loggerinst.info("    ... activation key not found, using given username and password")
            else:
                loggerinst.info("    ... activation key not found, username and password required")

            if tool_opts.username:
                loggerinst.info("    ... username detected")
                username = tool_opts.username
            else:
                username = ""
                while not username:
                    username = utils.prompt_user("Username: ")

            registration_attributes["username"] = username

            if tool_opts.password:
                loggerinst.info("    ... password detected")
                password = tool_opts.password
            else:
                password = ""
                while not password:
                    password = utils.prompt_user("Password: ", password=True)

            registration_attributes["password"] = password

        if tool_opts.rhsm_hostname:
            loggerinst.debug("    ... using custom RHSM hostname")
            registration_attributes["rhsm_hostname"] = tool_opts.rhsm_hostname
        if tool_opts.rhsm_port:
            loggerinst.debug("    ... using custom RHSM port")
            registration_attributes["rhsm_port"] = tool_opts.rhsm_port
        if tool_opts.rhsm_prefix:
            loggerinst.debug("    ... using custom RHSM prefix")
            registration_attributes["rhsm_prefix"] = tool_opts.rhsm_prefix

        return cls(**registration_attributes)

    @property
    def connection_opts(self):
        """
        This property is a dbus.Dictionary that contains the connection options for RHSM
        dbus calls.

        Set :attr:`server_url` to affect this value.
        """
        connection_opts = {}

        if self.rhsm_hostname:
            connection_opts["host"] = self.rhsm_hostname

        if self.rhsm_port is not None:
            connection_opts["port"] = self.rhsm_port

        if self.rhsm_prefix:
            connection_opts["handler"] = self.rhsm_prefix

        connection_opts = dbus.Dictionary(connection_opts, signature="sv", variant_level=1)
        return connection_opts

    def __call__(self):
        """
        Use dbus to register the system with subscription-manager.

        Status of dbus on various platforms:
            * RHEL7:
                * dbus-1.10.24 is installed and run by default
                * dbus-python-1.1.9 is available
            * RHEL8 & RHEL9
                * dbus-1.12.x is installed and run by default
                * python3-dbus-1.2.x is available

        .. seealso::
            Documentation for the subscription-manager dbus API:
            https://www.candlepinproject.org/docs/subscription-manager/dbus_objects.html
        """
        # Note: dbus doesn't understand empty python dicts. Use dbus.Dictionary({}, signature="ss")
        # if we need one in the future.
        REGISTER_OPTS_DICT = dbus.Dictionary({}, signature="sv", variant_level=1)

        loggerinst.debug("Getting a handle to the system dbus")
        system_bus = dbus.SystemBus()

        # Create a new bus so we can talk to rhsm privately (For security:
        # talking on the system bus might be eavesdropped in certain scenarios)
        loggerinst.debug("Getting a subscription-manager RegisterServer object from dbus")
        register_server = system_bus.get_object("com.redhat.RHSM1", "/com/redhat/RHSM1/RegisterServer")
        loggerinst.debug("Starting a private DBus to talk to subscription-manager")
        address = register_server.Start(
            i18n.SUBSCRIPTION_MANAGER_LOCALE,
            dbus_interface="com.redhat.RHSM1.RegisterServer",
        )

        try:
            # Use the private bus to register the machine
            loggerinst.debug("Connecting to the private DBus")
            private_bus = dbus.connection.Connection(address)

            try:
                if self.password:
                    if self.org:
                        loggerinst.info("Organization: %s", utils.OBFUSCATION_STRING)
                    loggerinst.info("Username: %s", utils.OBFUSCATION_STRING)
                    loggerinst.info("Password: %s", utils.OBFUSCATION_STRING)
                    loggerinst.info("Connection Options: %s", self.connection_opts)
                    loggerinst.info("Locale settings: %s", i18n.SUBSCRIPTION_MANAGER_LOCALE)
                    args = (
                        self.org or "",
                        self.username,
                        self.password,
                        REGISTER_OPTS_DICT,
                        self.connection_opts,
                        i18n.SUBSCRIPTION_MANAGER_LOCALE,
                    )
                    private_bus.call_blocking(
                        "com.redhat.RHSM1",
                        "/com/redhat/RHSM1/Register",
                        "com.redhat.RHSM1.Register",
                        "Register",
                        "sssa{sv}a{sv}s",
                        args,
                        timeout=REGISTRATION_TIMEOUT,
                    )

                else:
                    loggerinst.info("Organization: %s", utils.OBFUSCATION_STRING)
                    loggerinst.info("Activation Key: %s", utils.OBFUSCATION_STRING)
                    loggerinst.info("Connection Options: %s", self.connection_opts)
                    loggerinst.info("Locale settings: %s", i18n.SUBSCRIPTION_MANAGER_LOCALE)
                    args = (
                        self.org,
                        [self.activation_key],
                        REGISTER_OPTS_DICT,
                        self.connection_opts,
                        i18n.SUBSCRIPTION_MANAGER_LOCALE,
                    )
                    private_bus.call_blocking(
                        "com.redhat.RHSM1",
                        "/com/redhat/RHSM1/Register",
                        "com.redhat.RHSM1.Register",
                        "RegisterWithActivationKeys",
                        "sasa{sv}a{sv}s",
                        args,
                        timeout=REGISTRATION_TIMEOUT,
                    )

            except dbus.exceptions.DBusException as e:
                # Sometimes we get NoReply but the registration has succeeded.
                # Check the registration status before deciding if this is an error.
                if e.get_dbus_name() == "org.freedesktop.DBus.Error.NoReply":
                    # We need to set the connection opts in config before
                    # checking for registration otherwise we might ask the
                    # wrong server if the host is registered.
                    self._set_connection_opts_in_config()

                    if not is_registered():
                        # Host is not registered so re-raise the error
                        raise
                else:
                    raise
                # Host was registered so continue
            else:
                # On success, we need to set the connection opts as well
                self._set_connection_opts_in_config()

        finally:
            # Always shut down the private bus
            loggerinst.debug("Shutting down private DBus instance")
            register_server.Stop(
                i18n.SUBSCRIPTION_MANAGER_LOCALE,
                dbus_interface="com.redhat.RHSM1.RegisterServer",
            )

    def _set_connection_opts_in_config(self):
        """
        Set the connection opts in the rhsm config.

        The command line subscription-manager register command sets the
        config but the DBus API does not.  We need to set it so that
        subsequent subscription-manager cli calls will use the same connection
        settings.
        """
        # DBus policies are preventing the following from working.
        # Implement this as calls to the subscription-manager CLI for now.
        #
        # config_object = system_bus.get_object("com.redhat.RHSM1", "/com/redhat/RHSM1/Config")

        # for option, value in self.connection_opts.items():
        #     config_object.Set(
        #         CONNECT_OPT_NAME_TO_CONFIG_KEY[option],
        #         value,
        #         i18n.SUBSCRIPTION_MANAGER_LOCALE,
        #         dbus_interface="com.redhat.RHSM1.ConfigServer",
        #     )
        if self.connection_opts:
            loggerinst.info("Setting RHSM connection configuration.")
            sub_man_config_command = ["subscription-manager", "config"]
            for option, value in self.connection_opts.items():
                sub_man_config_command.append("--%s=%s" % (CONNECT_OPT_NAME_TO_CONFIG_KEY[option], value))

            output, ret_code = utils.run_subprocess(sub_man_config_command, print_cmd=True)
            if ret_code != 0:
                raise ValueError("Error setting the subscription-manager connection configuration: %s" % output)

            loggerinst.info("Successfully set RHSM connection configuration.")


def is_registered():
    """Check if the machine we're running on is registered with subscription-manager."""
    loggerinst.debug("Checking whether the host was registered.")
    output, ret_code = utils.run_subprocess(["subscription-manager", "identity"])

    # Registered: ret_code 0 and output like:
    # system identity: 36dad222-5002-45ba-8840-f41351294213
    # name: c2r-20220816124728
    # org name: 13460994
    # org ID: 13460994
    if ret_code == 0:
        loggerinst.debug("Host was registered.")
        return True

    # Unregistered: ret_code 1 and output like:
    # This system is not yet registered. Try 'subscription-manager register --help' for more information.
    loggerinst.debug("Host was not registered.")
    return False


def install_rhel_subscription_manager(pkgs_to_install):
    """
    Install the RHEL versions of the subscription-manager packages.

    ..seealso:: :func:`_relevant_subscription_manager_pkgs` for the list of
    packages that we install.

    ..warning::
        With enabling the client-tools repo we can't ensure that on CentOS
        Linux 7 the subscription-manager-rhsm-certificates is downloaded from
        the client-tools repo and not from the CentOS Linux 7 repo.

        The thing is that the CentOS one is missing the Red Hat certificate
        /etc/rhsm/ca/redhat-uep.pem which is necessary for being able to
        register the system to Red Hat Subscription Management (sometimes
        referred to as Customer Portal). However, the
        :class:`InstallRedHatCertForYumRepositories` action takes care of that
        shortcoming by installing the certificate.
    """
    backedup_reposdir = backup.get_backedup_system_repos()
    varsdir = DEFAULT_YUM_VARS_DIR if system_info.version.major == 7 else DEFAULT_DNF_VARS_DIR
    backedup_varsdir = os.path.join(backup.BACKUP_DIR, hashlib.md5(varsdir.encode()).hexdigest())

    setopts = []
    # Oracle Linux 7 needs to set the exclude option to avoid installing the
    # rhc-client-tools package instead of subscription-manager, as it is marked
    # as obsolete in the subscription-manager specfile for OL7. This option in
    # yum will make sure to ignore the rhn-client-tools package and install the
    # correct packages we are requesting.
    if system_info.id == "oracle" and system_info.version.major == 7:
        setopts.append("exclude=rhn-client-tools")

    client_tools_repofile_path = None
    if system_info.id == "centos" and system_info.version.major == 8:
        client_tools_repofile_path = repo.write_temporary_repofile(_CLIENT_TOOLS_RHEL_8_5_REPO)
    else:
        repofile_url = _CLIENT_TOOLS_REPOFILE_MAPPING[system_info.version.major]
        contents = repo.download_repofile(repofile_url)
        client_tools_repofile_path = repo.write_temporary_repofile(contents)

    reposdir = [os.path.dirname(client_tools_repofile_path), backedup_reposdir]
    setopts.append("reposdir=%s" % ",".join(reposdir))
    setopts.append("varsdir=%s" % backedup_varsdir)
    installed_pkg_set = RestorablePackageSet(
        pkgs_to_install,
        custom_releasever=system_info.version.major,
        set_releasever=True,
        setopts=setopts,
    )
    backup.backup_control.push(installed_pkg_set)


def is_sca_enabled():
    """
    Check if Simple Content Access has been enabled for this system.

    :returns: True if Simple Content Access is enabled.
    :rtype: bool
    """
    output, _ = utils.run_subprocess(["subscription-manager", "status"], print_output=False)
    if "content access mode is set to simple content access." in output.lower():
        return True
    return False


def is_subscription_attached():
    """
    Check if there is a current subscription attached by executing 'subscription-manager list --consumed' and checking
    the output.

    :returns: True if there is a current subscription. False if output is 'No consumed subscription pools were found.'
    :rtype: bool
    """
    output, _ = utils.run_subprocess(["subscription-manager", "list", "--consumed"], print_output=False)
    if "no consumed subscription pools were found." in output.lower():
        return False
    return True


def attach_subscription():
    """Attach a specific subscription to the registered OS. If no
    subscription ID has been provided through command line, let the user
    interactively choose one.
    """
    # check if SCA is enabled
    if is_sca_enabled():
        loggerinst.info("Simple Content Access is enabled, skipping subscription attachment")
        if tool_opts.pool:
            loggerinst.warning(
                "Because Simple Content Access is enabled the subscription specified by the pool ID will not be attached."
            )
        return True

    if tool_opts.activation_key:
        loggerinst.info("Using the activation key provided through the command line...")
        return True
    pool = ["subscription-manager", "attach"]
    if tool_opts.auto_attach:
        pool.append("--auto")
        loggerinst.info("Auto-attaching compatible subscriptions to the system ...")
    elif tool_opts.pool:
        # The subscription pool ID has been passed through a command line
        # option
        pool.extend(["--pool", tool_opts.pool])
        loggerinst.info("Attaching provided subscription pool ID to the system ...")
    elif not tool_opts.auto_attach and not tool_opts.pool:
        # defaulting to --auto similiar to the functioning of subscription-manager
        pool.append("--auto")
        loggerinst.info("Auto-attaching compatible subscriptions to the system ...")

    _, ret_code = utils.run_subprocess(pool)

    if ret_code != 0:
        # Unsuccessful attachment, e.g. the pool ID is incorrect or the
        # number of purchased attachments has been depleted.
        loggerinst.critical_no_exit(
            "Unsuccessful attachment of a subscription. Please refer to https://access.redhat.com/management/"
            " where you can either enable the SCA, create an activation key, or find a Pool ID of the subscription"
            " you wish to use and pass it to convert2rhel through the `--pool` CLI option."
        )
        raise exceptions.CriticalError(
            id_="FAILED_TO_ATTACH_SUBSCRIPTION",
            title="Failed to attach a subscription to the system.",
            description="convert2rhel was unable to attach a subscription to the system. An attached subscription is required for RHEL package installation.",
            remediations="Refer to https://access.redhat.com/management/ where you can enable Simple Content Access, create an activation key, or find a Pool ID of the subscription you wish to use and pass it to convert2rhel through the `--pool` CLI option.",
        )
    return True


def get_pool_id(sub_raw_attrs):
    """Parse the input multiline string holding subscription attributes to distill the pool ID."""
    pool_id = re.search(r"^Pool ID:\s+(.*?)$", sub_raw_attrs, re.MULTILINE | re.DOTALL)
    if pool_id:
        return pool_id.group(1)

    loggerinst.critical("Cannot parse the subscription pool ID from string:\n%s" % sub_raw_attrs)


def verify_rhsm_installed():
    """Make sure that subscription-manager has been installed."""
    if not pkghandler.get_installed_pkg_information("subscription-manager"):
        loggerinst.critical_no_exit(
            "The subscription-manager package is not installed correctly. You could try manually installing it before running convert2rhel"
        )
        raise exceptions.CriticalError(
            id_="FAILED_TO_VERIFY_SUBSCRIPTION_MANAGER",
            title="Failed to verify subscription-manager package.",
            description="The subscription-manager package is not installed correctly. Therefore, the pre-conversion analysis cannot verify that the correct package is installed on your system.",
            remediations="Manually installing subscription-manager before running convert2rhel.",
        )
    else:
        loggerinst.info("subscription-manager installed correctly.")


def disable_repos():
    """Before enabling specific repositories, all repositories should be
    disabled. This can be overriden by the --disablerepo option.
    """
    cmd = ["subscription-manager", "repos"]
    disabled_repos = ["*"] if not tool_opts.disablerepo else tool_opts.disablerepo
    disable_cmd = ["".join("--disable=" + repo) for repo in disabled_repos]
    cmd.extend(disable_cmd)
    output, ret_code = utils.run_subprocess(cmd, print_output=False)
    if ret_code != 0:
        loggerinst.critical_no_exit("Could not disable subscription-manager repositories:\n%s" % output)
        raise exceptions.CriticalError(
            id_="FAILED_TO_DISABLE_SUBSCRIPTION_MANAGER_REPOSITORIES",
            title="Could not disable repositories through subscription-manager.",
            description="As part of the conversion process, convert2rhel disables all current subscription-manager repositories and enables only repositories required for the conversion. convert2rhel was unable to disable these repositories, and the conversion is unable to proceed.",
            diagnosis="Failed to disable repositories: %s." % (output),
        )

    loggerinst.info("Repositories disabled.")


def enable_repos(rhel_repoids):
    """
    By default, enable the standard Red Hat CDN RHEL repository IDs using
    subscription-manager. This can be overriden by the --enablerepo option.

    .. note::
        If the system matches our criteria of a EUS release, then we will try
        to enable the EUS repoistories first, if that fails, we try to enable
        the default repositories, this way, the user will progress in the
        conversion.

        If the user specified the repositories to be enabled through
        --enablerepo, then the above logic is not applied.

    :param rhel_repoids: List of repositories to enable through
        subscription-manager.
    :type rhel_repoids: list[str]
    """
    if tool_opts.enablerepo:
        repos_to_enable = tool_opts.enablerepo
    else:
        repos_to_enable = rhel_repoids

    if repos_to_enable == system_info.eus_rhsm_repoids:
        try:
            loggerinst.info(
                "The system version corresponds to a RHEL Extended Update Support (EUS) release. "
                "Trying to enable RHEL EUS repositories."
            )
            # Try first if it's possible to enable EUS repoids. Otherwise try
            # enabling the default RHSM repoids. Otherwise, if it raiess an
            # exception, try to enable the default rhsm-repos
            submgr_enable_repos(repos_to_enable)
        except SystemExit:
            loggerinst.info(
                "The RHEL EUS repositories are not possible to enable.\n"
                "Trying to enable standard RHEL repositories as a fallback."
            )
            # Fallback to the default_rhsm_repoids
            repos_to_enable = system_info.default_rhsm_repoids
            submgr_enable_repos(repos_to_enable)
    else:
        # This could be either the default_rhsm repos or any user specific
        # repoids
        submgr_enable_repos(repos_to_enable)

    system_info.submgr_enabled_repos = repos_to_enable


def submgr_enable_repos(repos_to_enable):
    """Go through subscription manager repos and try to enable them through subscription-manager."""
    enable_cmd = ["subscription-manager", "repos"]
    for repo in repos_to_enable:
        enable_cmd.append("--enable=%s" % repo)
    output, ret_code = utils.run_subprocess(enable_cmd, print_output=False)
    if ret_code != 0:
        loggerinst.critical("Repositories were not possible to enable through subscription-manager:\n%s" % output)
    loggerinst.info("Repositories enabled through subscription-manager")


def needed_subscription_manager_pkgs():
    """
    Packages needed for subscription-manager which are not installed.

    :returns: A list of package names which are subscription-manager related and not presently
        installed.
    :rtype: list of str
    """
    # Packages to check for to determine if subscription-manager is installed
    subscription_manager_pkgs = _relevant_subscription_manager_pkgs()

    # filter pkgs which already installed out of the list of pkgs we will install.
    installed_submgr_pkgs = []
    to_install_pkgs = set()
    for pkg in subscription_manager_pkgs:
        installed_pkgs = pkghandler.get_installed_pkg_information(pkg)
        installed_submgr_pkgs.extend(installed_pkgs)
        if not installed_pkgs:
            to_install_pkgs.add(pkg)

    to_install_pkgs = list(to_install_pkgs)

    # WARNING: Use to_install_pkgs for things that are returned.
    # **installed_submgr_pkgs can only be used for human-readable display**.
    # to_install_pkgs has properly dealt with arch but
    # installed_submgr_pkgs has lost its arch'd information so we
    # can't do comparisons with it unless we query
    # `get_installed_pkg_information()` again.
    installed_submgr_pkgs = [pkg.nevra.name for pkg in installed_submgr_pkgs]

    loggerinst.debug("Need the following packages: %s" % utils.format_sequence_as_message(subscription_manager_pkgs))
    loggerinst.debug("Detected the following packages: %s" % utils.format_sequence_as_message(installed_submgr_pkgs))

    loggerinst.debug("Packages we will install: %s" % utils.format_sequence_as_message(to_install_pkgs))

    return to_install_pkgs


def _relevant_subscription_manager_pkgs():
    """
    Subscription-manager related packages that we check for and install.

    :returns: a list of package names which we check are installed so subscription-manager will run.
    :rtype: list of strings
    """
    relevant_pkgs = [
        "subscription-manager",
    ]

    if system_info.version.major == 7:
        relevant_pkgs += ["subscription-manager-rhsm", "subscription-manager-rhsm-certificates", "python-syspurpose"]

    elif system_info.version.major == 8:
        relevant_pkgs += [
            "python3-subscription-manager-rhsm",
            "dnf-plugin-subscription-manager",
            "python3-syspurpose",
            "python3-cloud-what",
            "json-c.x86_64",  # there's also an i686 version we don't need unless the json-c.i686 is already installed
            "subscription-manager-rhsm-certificates",
        ]

    elif system_info.version.major >= 9:
        relevant_pkgs += [
            "libdnf-plugin-subscription-manager",
            "python3-subscription-manager-rhsm",
            "python3-cloud-what",
            "subscription-manager-rhsm-certificates",
        ]

    if system_info.is_rpm_installed("json-c.i686"):
        # In case the json-c.i686 is installed we need to download it together with its x86_64 companion. The reason
        # is that it's not possible to install a 64-bit library that has a different version from the 32-bit one.
        relevant_pkgs.append("json-c.i686")

    return relevant_pkgs


def lock_releasever_in_rhel_repositories():
    """Lock the releasever in the RHEL repositories located under /etc/yum.repos.d/redhat.repo

    After converting to a RHEL EUS minor version, we need to lock the releasever in the redhat.repo file
    to prevent future errors such as, running `yum update` and not being able to find the repositories metadata.

    .. note::
        This function should only run if the system corresponds to a RHEL EUS version to make sure the converted system
        keeps receiving updates for the specific EUS minor version instead of the latest minor version which is the
        default.
    """

    # We only lock the releasever on rhel repos if we detect that the running system is an EUS correspondent and if
    # rhsm is used, otherwise, there's no need to lock the releasever as the subscription-manager won't be available.
    if system_info.eus_system and not tool_opts.no_rhsm:
        loggerinst.info(
            "Updating /etc/yum.repos.d/rehat.repo to point to RHEL %s instead of the default latest minor version."
            % system_info.releasever
        )
        cmd = [
            "subscription-manager",
            "release",
            "--set=%s" % system_info.releasever,
        ]

        output, ret_code = utils.run_subprocess(cmd, print_output=False)
        if ret_code != 0:
            loggerinst.warning(
                "Locking RHEL repositories failed with return code %d and message:\n%s",
                ret_code,
                output,
            )
        else:
            loggerinst.info("RHEL repositories locked to the %s minor version." % system_info.releasever)
    else:
        loggerinst.info("Skipping locking RHEL repositories to a specific EUS minor version.")


def update_rhsm_custom_facts():
    """Update the RHSM custom facts in the candlepin server.

    This function has the intention to synchronize the facts collected throughout
    the conversion with the candlepin server, thus, propagating the
    "breadcrumbs" from convert2rhel as RHSM facts.
    """
    if not tool_opts.no_rhsm:
        loggerinst.info("Updating RHSM custom facts collected during the conversion.")
        cmd = ["subscription-manager", "facts", "--update"]
        output, ret_code = utils.run_subprocess(cmd, print_output=False)

        if ret_code != 0:
            loggerinst.warning(
                "Failed to update the RHSM custom facts with return code '%s' and output '%s'.",
                ret_code,
                output,
            )
        else:
            loggerinst.info("RHSM custom facts uploaded successfully.")
    else:
        loggerinst.info("Skipping updating RHSM custom facts.")


def get_rhsm_facts():
    """
    Open RHSM facts file and parse the facts

    :returns dict: The RHSM facts.
    """
    rhsm_facts = {}
    if tool_opts.no_rhsm:
        loggerinst.info("Ignoring RHSM facts collection. --no-rhsm is used.")
        return rhsm_facts

    loggerinst.info("Reading RHSM facts file.")
    try:
        with open(RHSM_FACTS_FILE, mode="r") as handler:
            rhsm_facts = json.load(handler)
            loggerinst.info("RHSM facts loaded.")
    except (IOError, ValueError) as e:
        loggerinst.critical_no_exit(
            "Failed to get the RHSM facts : %s." % e,
        )
    return rhsm_facts
