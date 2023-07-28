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

import logging
import os
import re
import shutil

from collections import namedtuple
from time import sleep

import dbus
import dbus.connection
import dbus.exceptions

from convert2rhel import backup, i18n, pkghandler, utils
from convert2rhel.redhatrelease import os_release_file
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


loggerinst = logging.getLogger(__name__)

SUBMGR_RPMS_DIR = os.path.join(utils.DATA_DIR, "subscription-manager")
_RHSM_TMP_DIR = os.path.join(utils.TMP_DIR, "rhsm")
_UBI_7_REPO_CONTENT = (
    "[ubi-7-convert2rhel]\n"
    "name=Red Hat Universal Base Image 7 - added by Convert2RHEL\n"
    "baseurl=https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi/server/7/7Server/$basearch/os/\n"
    "gpgcheck=1\n"
    "enabled=1\n"
)
_UBI_7_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "ubi_7.repo")
# We are using UBI 8 instead of CentOS Linux 8 because there's a bug in subscription-manager-rhsm-certificates on CentOS Linux 8
# https://bugs.centos.org/view.php?id=17907
_UBI_8_REPO_CONTENT = (
    "[ubi-8-baseos-convert2rhel]\n"
    "name=Red Hat Universal Base Image 8 - BaseOS added by Convert2RHEL\n"
    "baseurl=https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi8/8/$basearch/baseos/os/\n"
    "gpgcheck=1\n"
    "enabled=1\n"
)
_UBI_8_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "ubi_8.repo")

# Directory and file that is used for the convert2rhel.repo ssl cert that we
# tell customers to use to install convert2rhel:
_RHSM_REPO_CAFILE_DIR = "/etc/rhsm/ca/"
_CONVERT2RHEL_REPO_CAFILE_PATH = os.path.join(utils.DATA_DIR, "redhat-uep.pem")

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


_SUBMGR_PKG_REMOVED_IN_CL_85 = "subscription-manager-initial-setup-addon"


class UnregisterError(Exception):
    """Raised with problems unregistering a system."""


class StopRhsmError(Exception):
    """Raised with problems stopping the rhsm daemon."""


def subscribe_system():
    """Register and attach a specific subscription to OS."""
    while True:
        register_system()
        if attach_subscription():
            break
        # Clear potentially wrong credentials
        tool_opts.username = None
        tool_opts.password = None


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
            # The file /etc/os-release is needed for subscribing the system and is being removed with
            # <system-name>-release package in one of the steps before
            # RHELC-16
            os_release_file.restore(rollback=False)
            registration_cmd()
            # Need to remove the file, if it would stay there would be leftover /etc/os-release.rpmorig
            # after conversion
            # RHELC-16
            os_release_file.remove()
            loggerinst.info("System registration succeeded.")
        except KeyboardInterrupt:
            # When the user hits Control-C to exit, we shouldn't retry
            raise
        except Exception as e:
            loggerinst.info("System registration failed with error: %s" % str(e))
            sleep(REGISTRATION_ATTEMPT_DELAYS[attempt])
            attempt += 1
            continue

        break

    else:  # While-else
        # We made the maximum number of subscription-manager retries and still failed
        loggerinst.critical("Unable to register the system through subscription-manager.")

    return None


def _stop_rhsm():
    """Stop the rhsm service."""
    cmd = ["/bin/systemctl", "stop", "rhsm"]
    output, ret_code = utils.run_subprocess(cmd, print_output=False)
    if ret_code != 0:
        raise StopRhsmError("Stopping RHSM failed with code: %s; output: %s" % (ret_code, output))
    loggerinst.info("RHSM service stopped.")


class RegistrationCommand(object):
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

                    if not _is_registered():
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

        The command line subscriptioVn-manager register command sets the
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


def _is_registered():
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


def replace_subscription_manager():
    """Remove any previously installed subscription-manager packages and install the RHEL ones.

    Make sure the system is unregistered before removing the subscription-manager as not doing so would leave the
    system to be still registered on the server side, making it dificult for an admin to unregister it afterwards.
    """
    if tool_opts.keep_rhsm:
        loggerinst.info("Skipping due to the use of --keep-rhsm.")
        return

    if not os.path.isdir(SUBMGR_RPMS_DIR) or not os.listdir(SUBMGR_RPMS_DIR):
        loggerinst.critical("The %s directory does not exist or is empty." % SUBMGR_RPMS_DIR)

    try:
        unregister_system()
    except UnregisterError as e:
        loggerinst.warning(str(e))

    remove_original_subscription_manager()
    install_rhel_subscription_manager()


def remove_original_subscription_manager():
    loggerinst.info("Removing installed subscription-manager/katello-ca-consumer packages.")
    # python3-subscription-manager-rhsm, dnf-plugin-subscription-manager, subscription-manager-rhsm-certificates, etc.
    submgr_pkgs = pkghandler.get_installed_pkg_objects("*subscription-manager*")
    # The python-syspurpose, python3-syspurpose, and python3-cloud-what packages are also built out of
    # the subscription-manager SRPM.
    submgr_pkgs += pkghandler.get_installed_pkg_objects("python*-syspurpose")
    submgr_pkgs += pkghandler.get_installed_pkg_objects("python3-cloud-what")
    # Satellite-server related package
    submgr_pkgs += pkghandler.get_installed_pkg_objects("katello-ca-consumer*")

    if not submgr_pkgs:
        loggerinst.info("No packages related to subscription-manager installed.")
        return

    loggerinst.info("We will now uninstall the following subscription-manager/katello-ca-consumer packages:\n")
    pkghandler.print_pkg_info(submgr_pkgs)
    submgr_pkg_names = [pkg.name for pkg in submgr_pkgs]

    if system_info.id == "centos" and system_info.version.major == 8 and system_info.version.minor == 5:
        if _SUBMGR_PKG_REMOVED_IN_CL_85 in submgr_pkg_names:
            # The package listed in _SUBMGR_PKG_REMOVED_IN_CL_85 has been
            # removed from CentOS Linux 8.5 and causes conversion to fail if
            # it's installed on that system because it's not possible to back it up.
            # https://bugzilla.redhat.com/show_bug.cgi?id=2046292
            backup.remove_pkgs([_SUBMGR_PKG_REMOVED_IN_CL_85], backup=False, critical=False)
            submgr_pkg_names.remove(_SUBMGR_PKG_REMOVED_IN_CL_85)

    # Remove any other subscription-manager packages present on the system
    backup.remove_pkgs(submgr_pkg_names, critical=False)


def install_rhel_subscription_manager():
    loggerinst.info("Checking for subscription-manager RPMs.")
    rpms_to_install = [os.path.join(SUBMGR_RPMS_DIR, filename) for filename in os.listdir(SUBMGR_RPMS_DIR)]

    if not rpms_to_install:
        loggerinst.warning("No RPMs found in %s." % SUBMGR_RPMS_DIR)
        return

    # We need to make sure the redhat-uep.pem file exists since the convert2rhel
    # yum repo file uses it.
    _check_and_install_redhat_uep_pem()

    # These functions have to be called before installation of the
    # subscription-manager packages, otherwise
    # `pkghandler.filter_installed_pkgs()` would return every single package
    # that is listed in `rpms_to_install` and we don't want this to happen. We
    # want to know about the packages that were installed before the
    # installation of subscription-manager.
    pkg_names = pkghandler.get_pkg_names_from_rpm_paths(rpms_to_install)
    pkgs_to_not_track = pkghandler.filter_installed_pkgs(pkg_names)

    loggerinst.info("Installing subscription-manager RPMs.")
    _, ret_code = pkghandler.call_yum_cmd(
        # We're using distro-sync as there might be various versions of the subscription-manager pkgs installed
        # and we need these packages to be replaced with the provided RPMs from RHEL.
        command="install",
        args=rpms_to_install,
        print_output=True,
        # When installing subscription-manager packages, the RHEL repos are not available yet => we need to use
        # the repos that are available on the system
        enable_repos=[],
        disable_repos=[],
        # When using the original system repos, we need YUM/DNF to expand the $releasever by itself
        set_releasever=False,
    )
    if ret_code:
        loggerinst.critical("Failed to install subscription-manager packages. See the above yum output for details.")

    loggerinst.info("\nPackages installed:\n%s" % "\n".join(rpms_to_install))

    track_installed_submgr_pkgs(pkg_names, pkgs_to_not_track)


def _check_and_install_redhat_uep_pem():
    """
    Install the redhat-uep.pem certificate if it is needed.

    We need this for the convert2rhel repo if the user installed using the
    convert2rhel.repo file:
    https://ftp.redhat.com/redhat/convert2rhel/8/convert2rhel.repo

    This is a workaround for https://issues.redhat.com/browse/RHELC-744
    When we make uninstalling and reinstalling the RHEL subscription-manager
    packages a single step process, we will no longer need this as there will
    always be a redhat-uep.pem available from a package.
    """
    rhsm_ca_file = os.path.join(_RHSM_REPO_CAFILE_DIR, "redhat-uep.pem")
    if not os.path.exists(rhsm_ca_file):
        # Note: this mkdir_p is secure because CONVERT2RHEL_REPO_CAFILE_DIR is
        # a constant that does not have any world-writable components.
        utils.mkdir_p(_RHSM_REPO_CAFILE_DIR)

        # Copy the CA file into place because the convert2rhel repo
        # configuration needs it.
        shutil.copy2(_CONVERT2RHEL_REPO_CAFILE_PATH, _RHSM_REPO_CAFILE_DIR)


def track_installed_submgr_pkgs(installed_pkg_names, pkgs_to_not_track):
    """Tracking newly installed subscription-manager pkgs to be able to remove them during a rollback if needed.

    :param installed_pkg_names: List of packages that were installed on the system.
    :type installed_pkg_names: list[str]
    :param pkgs_to_not_track: List of packages that needs to be removed from tracking.
    :type pkgs_to_not_track: list[str]
    """
    pkgs_to_track = []
    for installed_pkg in installed_pkg_names:
        if installed_pkg not in pkgs_to_not_track:
            pkgs_to_track.append(installed_pkg)
        else:
            # Don't track packages that were present on the system before the installation
            loggerinst.debug("Skipping tracking previously installed package: %s" % installed_pkg)

    loggerinst.debug("Tracking installed packages: %r" % pkgs_to_track)
    backup.changed_pkgs_control.track_installed_pkgs(pkgs_to_track)


def attach_subscription():
    """Attach a specific subscription to the registered OS. If no
    subscription ID has been provided through command line, let the user
    interactively choose one.
    """
    # TODO: Support attaching multiple pool IDs.

    # check if SCA is enabled
    output, _ = utils.run_subprocess(["subscription-manager", "status"], print_output=False)
    if "content access mode is set to simple content access." in output.lower():
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
        loggerinst.critical(
            "Unsuccessful attachment of a subscription. Please refer to https://access.redhat.com/management/"
            " where you can either enable the SCA, create an activation key, or find a Pool ID of the subscription"
            " you wish to use and pass it to convert2rhel through the --pool CLI option."
        )
    return True


def get_pool_id(sub_raw_attrs):
    """Parse the input multiline string holding subscription attributes to distill the pool ID."""
    pool_id = re.search(r"^Pool ID:\s+(.*?)$", sub_raw_attrs, re.MULTILINE | re.DOTALL)
    if pool_id:
        return pool_id.group(1)

    loggerinst.critical("Cannot parse the subscription pool ID from string:\n%s" % sub_raw_attrs)


def print_avail_subs(subs):
    """Print the subscriptions available to the user so they can choose one."""
    loggerinst.info("Choose one of your subscriptions that is to be used for converting this system to RHEL:")
    for index, sub in enumerate(subs):
        index += 1
        loggerinst.info("\n======= Subscription number %d =======\n\n%s" % (index, sub.sub_raw))


def get_avail_repos():
    """Get list of all the repositories (their IDs) currently available for
    the registered system through subscription-manager.
    """
    repos_raw, _ = utils.run_subprocess(["subscription-manager", "repos"], print_output=False)
    return list(get_repo(repos_raw))


def get_repo(repos_raw):
    """Generator that parses the raw string of available repositores and
    provides the repository IDs, one at a time.
    """
    for repo_id in re.findall(r"Repo ID:\s+(.*?)\n", repos_raw, re.DOTALL | re.MULTILINE):
        yield repo_id


def verify_rhsm_installed():
    """Make sure that subscription-manager has been installed."""
    if not pkghandler.get_installed_pkg_objects("subscription-manager"):
        if tool_opts.keep_rhsm:
            loggerinst.critical(
                "When using the --keep-rhsm option, the subscription-manager needs to be installed before"
                " executing convert2rhel."
            )
        else:
            # Most probably this condition will not be hit. If the installation of subscription-manager fails, the
            # conversion stops already at that point.
            loggerinst.critical("The subscription-manager package is not installed correctly.")
    else:
        loggerinst.info("subscription-manager installed correctly.")


def disable_repos():
    """Before enabling specific repositories, all repositories should be
    disabled. This can be overriden by the --disablerepo option.
    """
    disable_cmd = ["subscription-manager", "repos"]
    disable_repos = []
    for repo in tool_opts.disablerepo:
        disable_repos.append("--disable=%s" % repo)

    if not disable_repos:
        # Default is to disable all repos to make clean environment for
        # enabling repos later
        disable_repos.append("--disable=*")

    disable_cmd.extend(disable_repos)
    output, ret_code = utils.run_subprocess(disable_cmd, print_output=False)
    if ret_code != 0:
        loggerinst.critical("Repositories were not possible to disable through subscription-manager:\n%s" % output)
    loggerinst.info("Repositories disabled.")
    return


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
            _submgr_enable_repos(repos_to_enable)
        except SystemExit:
            loggerinst.info(
                "The RHEL EUS repositories are not possible to enable.\n"
                "Trying to enable standard RHEL repositories as a fallback."
            )
            # Fallback to the default_rhsm_repoids
            repos_to_enable = system_info.default_rhsm_repoids
            _submgr_enable_repos(repos_to_enable)
    else:
        # This could be either the default_rhsm repos or any user specific
        # repoids
        _submgr_enable_repos(repos_to_enable)

    system_info.submgr_enabled_repos = repos_to_enable


def _submgr_enable_repos(repos_to_enable):
    """Go through subscription manager repos and try to enable them through subscription-manager."""
    enable_cmd = ["subscription-manager", "repos"]
    for repo in repos_to_enable:
        enable_cmd.append("--enable=%s" % repo)
    output, ret_code = utils.run_subprocess(enable_cmd, print_output=False)
    if ret_code != 0:
        loggerinst.critical("Repositories were not possible to enable through subscription-manager:\n%s" % output)
    loggerinst.info("Repositories enabled through subscription-manager")


def rollback():
    """Rollback subscription related changes"""
    # Systems using Satellite 6.10 need to stay registered otherwise admins
    # will lose remote access from the Satellite server.
    loggerinst.task("Rollback: RHSM-related actions")
    if tool_opts.keep_rhsm:
        loggerinst.info("Skipping due to the use of --keep-rhsm.")
        return

    try:
        unregister_system()
    except UnregisterError as e:
        loggerinst.warning(str(e))
    except OSError:
        loggerinst.warning("subscription-manager not installed, skipping")


def check_needed_repos_availability(repo_ids_needed):
    """Check whether all the RHEL repositories needed for the system
    conversion are available through subscription-manager.
    """
    loggerinst.info("Verifying needed RHEL repositories are available ... ")
    avail_repos = get_avail_repos()
    loggerinst.info("Repositories available through RHSM:\n%s" % "\n".join(avail_repos) + "\n")
    non_avail_repos = []
    all_repos_avail = True

    for repo_id in repo_ids_needed:
        if repo_id not in avail_repos:
            # TODO: List the packages that would be left untouched
            loggerinst.warning(
                "Some repositories are not available: %s."
                " Some packages may not be replaced with their corresponding"
                " RHEL packages when converting. The converted system will end up"
                " with a mixture of packages from RHEL and your current distribution." % repo_id
            )
            non_avail_repos.append(repo_id)
            all_repos_avail = False

    if all_repos_avail:
        loggerinst.info("Needed RHEL repositories are available.")
    return non_avail_repos


def download_rhsm_pkgs():
    """Download all the packages necessary for a successful registration to the Red Hat Subscription Management.

    The packages are available in non-standard repositories, so additional repofiles need to be used. The downloaded
    RPMs are to be installed in a later stage of the conversion.
    """
    if tool_opts.keep_rhsm:
        loggerinst.info("Skipping due to the use of --keep-rhsm.")
        return
    utils.mkdir_p(_RHSM_TMP_DIR)

    pkgs_to_download = [
        "subscription-manager",
        "subscription-manager-rhsm-certificates",
    ]

    if system_info.version.major == 7:
        pkgs_to_download += ["subscription-manager-rhsm", "python-syspurpose"]
        _download_rhsm_pkgs(pkgs_to_download, _UBI_7_REPO_PATH, _UBI_7_REPO_CONTENT)

    elif system_info.version.major == 8:
        pkgs_to_download += [
            "python3-subscription-manager-rhsm",
            "dnf-plugin-subscription-manager",
            "python3-syspurpose",
            "python3-cloud-what",
            "json-c.x86_64",  # there's also an i686 version we don't need unless the json-c.i686 is already installed
        ]
        if system_info.is_rpm_installed("json-c.i686"):
            # In case the json-c.i686 is installed we need to download it together with its x86_64 companion. The reason
            # is that it's not possible to install a 64-bit library that has a different version from the 32-bit one.
            pkgs_to_download.append("json-c.i686")
        _download_rhsm_pkgs(pkgs_to_download, _UBI_8_REPO_PATH, _UBI_8_REPO_CONTENT)


def _download_rhsm_pkgs(pkgs_to_download, repo_path, repo_content):
    _log_rhsm_download_directory_contents(SUBMGR_RPMS_DIR, "before RHEL rhsm packages download")

    utils.store_content_to_file(filename=repo_path, content=repo_content)
    paths = utils.download_pkgs(pkgs_to_download, dest=SUBMGR_RPMS_DIR, reposdir=_RHSM_TMP_DIR)

    _log_rhsm_download_directory_contents(SUBMGR_RPMS_DIR, "after RHEL rhsm packages download")
    exit_on_failed_download(paths)


def _log_rhsm_download_directory_contents(directory, when_message):
    pkgs = ["<download directory does not exist>"]
    if os.path.isdir(SUBMGR_RPMS_DIR):
        pkgs = os.listdir(SUBMGR_RPMS_DIR)
    loggerinst.debug(
        "Contents of %s directory %s:\n%s",
        SUBMGR_RPMS_DIR,
        when_message,
        "\n".join(pkgs),
    )


def exit_on_failed_download(paths):
    if None in paths:
        loggerinst.critical(
            "Unable to download the subscription-manager package or its dependencies. See details of"
            " the failed yumdownloader call above. These packages are necessary for the conversion"
            " unless you use the --no-rhsm option."
        )


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
    if system_info.corresponds_to_rhel_eus_release() and not tool_opts.no_rhsm:
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
    if "CONVERT2RHEL_DISABLE_TELEMETRY" in os.environ:
        loggerinst.info("Telemetry disabled, skipping RHSM facts upload.")
        return

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
