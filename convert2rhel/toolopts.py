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

import optparse
import logging
from convert2rhel import rhelvariant
from convert2rhel import utils

class ToolOpts(object):
    def __init__(self):
        self.debug = False
        self.username = None
        self.password_file = None
        self.password = None
        self.disable_submgr = False
        self.enablerepo = []
        self.disablerepo = []
        self.pool = None
        self.variant = None
        self.serverurl = None
        self.autoaccept = None
        self.auto_attach = None
        self.restart = None
        self.activation_key = None
        self.org = None
        self.arch = None
        self.no_rpm_va = False

        # set True when credentials (username & password) are given through CLI
        self.credentials_thru_cli = False


class CLI(object):
    def __init__(self):
        self._parser = self._get_argparser()
        self._register_options()
        self._process_cli_options()

    @staticmethod
    def _get_argparser():
        usage = ("\n"
                 "  convert2rhel [-h]\n"
                 "  convert2rhel [-u username] [-p password | -f pswd_file]"
                 " [--pool pool_id | -a] [--disablerepo repoid] [--enablerepo"
                 " repoid] [-v variant] [--serverurl url] [--no-rpm-va]"
                 " [--debug] [--restart] [-y]\n"
                 "  convert2rhel [--disable-submgr] [--disablerepo repoid]"
                 " [--enablerepo repoid] [--no-rpm-va] [--debug] [--restart] [-y]\n"
                 "  convert2rhel [-k key] [-o organization] [--pool pool_id |"
                 " -a] [--disablerepo repoid] [--enablerepo repoid] [-v"
                 " variant] [--serverurl url] [--no-rpm-va] [--debug]"
                 " [--restart] [-y]")
        return optparse.OptionParser(conflict_handler='resolve',
                                     usage=usage,
                                     add_help_option=False)

    def _register_options(self):
        """Prescribe what command line options the tool accepts."""
        self._parser.add_option("-h", "--help", action="help", help="Show "
                                " help message and exit.")
        self._parser.add_option("--debug", action="store_true", help="Print"
                                " traceback in case of an abnormal exit and"
                                " messages that could help find an issue.")
        # Importing here instead of on top of the file to avoid cyclic dependency
        from convert2rhel.systeminfo import PRE_RPM_VA_LOG_FILENAME, POST_RPM_VA_LOG_FILENAME
        self._parser.add_option("--no-rpm-va", action="store_true", help="Skip gathering changed rpm files using"
                                " 'rpm -Va'. By default it's performed before and after the conversion with the output"
                                " stored in log files %s and %s. At the end of the conversion, these logs are compared"
                                " to show you what rpm files have been affected by the conversion."
                                % (PRE_RPM_VA_LOG_FILENAME, POST_RPM_VA_LOG_FILENAME))
        self._parser.add_option("--enablerepo", metavar="repoidglob",
                                action="append", help="Enable specific"
                                " repositories by ID or glob. For more repositories to enable, use this option"
                                " multiple times. If you don't use the --disable-submgr option, you can use this option"
                                " to override the default RHEL CDN repoids that convert2rhel enables through"
                                " subscription-manager.")
        self._parser.add_option("--disablerepo", metavar="repoidglob",
                                action="append", help="Disable specific"
                                " repositories by ID or glob. For more repositories to disable, use this option"
                                " multiple times. This option defaults to all repositories ('*').")
        group = optparse.OptionGroup(self._parser,
                                     "Subscription Manager Options",
                                     "The following options are specific to"
                                     "using subscription-manager.")
        group.add_option("-u", "--username", help="Username for the"
                         " subscription-manager. If neither --username nor"
                         " --activation-key option is used, the user"
                         " is asked to enter the username.")
        group.add_option("-p", "--password", help="Password for the"
                         " subscription-manager. If --password,"
                         " --password-from-file or --activationkey are not"
                         " used, the user is asked to enter the password.")
        group.add_option("-f", "--password-from-file", help="File containing"
                         " password for the subscription-manager in the plain"
                         " text form. It's an alternative to the --password"
                         " option.")
        group.add_option("-k", "--activationkey", help="Activation key used"
                         " for the system registration by the"
                         " subscription-manager. It requires to have the --org"
                         " option specified.")
        group.add_option("-o", "--org", help="Organization with which the"
                         " system will be registered by the"
                         " subscription-manager. A list of available"
                         " organizations is possible to obtain by running"
                         " 'subscription-manager orgs'. From the listed pairs"
                         " Name:Key, use the Key here.")
        group.add_option("-a", "--auto-attach", help="Automatically attach"
                         " compatible subscriptions to the system.",
                         action='store_true')
        group.add_option("--pool", help="Subscription pool ID. If not used,"
                         " the user is asked to choose from the available"
                         " subscriptions. A list of the available"
                         " subscriptions is possible to obtain by running"
                         " 'subscription-manager list --available'.")
        group.add_option("-v", "--variant", help="The RHEL variant to which"
                         " the system will be converted. Available variants"
                         " are: Server, Client, Workstation, ComputeNode. If"
                         " not used, the user is asked to choose a variant.")
        group.add_option("--serverurl", help="Use a custom Red Hat Subscription"
                         " Manager server URL to register the system with. If"
                         " not provided, the subscription-manager defaults will be"
                         " used.")
        self._parser.add_option_group(group)

        group = optparse.OptionGroup(self._parser,
                                     "Alternative Installation Options",
                                     "The following options are required if"
                                     " you do not intend on using"
                                     " subscription-manager")
        group.add_option("--disable-submgr", action="store_true",
                         help="Do not use the subscription-manager, use"
                         " custom repositories instead. See"
                         " --enablerepo/--disablerepo options. Without this"
                         " option, the subscription-manager is used to access"
                         " RHEL repositories by default. It requires to have"
                         " the --enablerepo specified.")
        self._parser.add_option_group(group)

        group = optparse.OptionGroup(self._parser, "Automation Options",
                                     "The following options are used to"
                                     " automate the installation")
        group.add_option("-r", "--restart", help="Restart the system"
                         " when it is successfully converted to RHEL to boot"
                         " the new RHEL kernel.", action='store_true')
        group.add_option("-y", help="Answer yes to all yes/no questions the"
                         " tool asks.", action='store_true')
        self._parser.add_option_group(group)

    def _process_cli_options(self):
        """Process command line options used with the tool."""
        loggerinst = logging.getLogger(__name__)
        parsed_opts, _ = self._parser.parse_args()

        global tool_opts  # pylint: disable=C0103
        if parsed_opts.debug:
            tool_opts.debug = True

        if parsed_opts.no_rpm_va:
            tool_opts.no_rpm_va = True

        if parsed_opts.username:
            tool_opts.username = parsed_opts.username

        if parsed_opts.password:
            tool_opts.password = parsed_opts.password

        if parsed_opts.password_from_file:
            tool_opts.password_file = parsed_opts.password_from_file
            tool_opts.password = utils.get_file_content(
                parsed_opts.password_from_file)

        if parsed_opts.enablerepo:
            tool_opts.enablerepo = parsed_opts.enablerepo
        if parsed_opts.disablerepo:
            tool_opts.disablerepo = parsed_opts.disablerepo
        if parsed_opts.disable_submgr:
            tool_opts.disable_submgr = True
            if not tool_opts.enablerepo:
                loggerinst.critical(
                    "Error: --enablerepo is required if --disable-submgr is passed ")
        if not tool_opts.disablerepo:
            # Default to disable every repo except:
            # - the ones passed through --enablerepo
            # - the ones enabled through subscription-manager based on convert2rhel config files
            tool_opts.disablerepo = ["*"]

        if parsed_opts.pool:
            tool_opts.pool = parsed_opts.pool

        if parsed_opts.variant:
            if not rhelvariant.is_variant_supported(parsed_opts.variant):
                loggerinst.critical("Error: Incorrect RHEL variant has been "
                                    " passed through command line.\nSupported"
                                    " variants are: %s."
                                    % ", ".join(
                                        rhelvariant.get_supported_variants()))
            tool_opts.variant = parsed_opts.variant

        if parsed_opts.serverurl:
            if parsed_opts.disable_submgr:
                loggerinst.warn("Ignoring the --serverurl option. It has no effect when --disable-submgr is used.")
            else:
                tool_opts.serverurl = parsed_opts.serverurl

        tool_opts.autoaccept = parsed_opts.y
        tool_opts.auto_attach = parsed_opts.auto_attach
        tool_opts.restart = parsed_opts.restart

        if parsed_opts.activationkey:
            tool_opts.activation_key = parsed_opts.activationkey

        if parsed_opts.org:
            tool_opts.org = parsed_opts.org

        if tool_opts.username and tool_opts.password:
            tool_opts.credentials_thru_cli = True


def print_non_interactive_opts():
    """Print command line options to be used for the next run of the tool
    to avoid the need of any interactive input during the system conversion.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("For the non-interactive use of the tool, run the"
                    " following command:")
    global tool_opts  # pylint: disable=C0103
    cmd = utils.get_executable_name()

    if tool_opts.disable_submgr:
        cmd += " --disable-submgr "
        for repo in tool_opts.disablerepo:
            cmd += " --disablerepo=%s " % repo
        for repo in tool_opts.enablerepo:
            cmd += " --enablerepo=%s " % repo
    else:
        if tool_opts.username:
            cmd += " -u %s" % tool_opts.username
            if tool_opts.password_file:
                pswd_opt = " -f %s" % tool_opts.password_file
            else:
                pswd_opt = " -p *****"
            cmd += pswd_opt
        if tool_opts.activation_key:
            cmd += " -k %s" % tool_opts.activation_key
        if tool_opts.org:
            cmd += " -o %s" % tool_opts.org
        cmd += " %s" % tool_opts.pool
    cmd += " -v %s" % tool_opts.variant
    cmd += " -y"
    loggerinst.info(cmd + "\n\n")


# Code to be executed upon module import
tool_opts = ToolOpts()  # pylint: disable=C0103
