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

import abc
import importlib
import itertools
import logging
import os
import os.path
import pkgutil
import re

from functools import cmp_to_key, wraps

import six

from convert2rhel import grub, pkgmanager, utils
from convert2rhel.pkghandler import (
    call_yum_cmd,
    compare_package_versions,
    get_installed_pkg_objects,
    get_pkg_fingerprint,
    get_total_packages_to_update,
)
from convert2rhel.repo import get_hardcoded_repofiles_dir
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import ask_to_continue, get_file_content, run_subprocess


logger = logging.getLogger(__name__)

KERNEL_REPO_RE = re.compile(r"^.+:(?P<version>.+).el.+$")
KERNEL_REPO_VER_SPLIT_RE = re.compile(r"\W+")
BAD_KERNEL_RELEASE_SUBSTRINGS = ("uek", "rt", "linode")

RPM_GPG_KEY_PATH = os.path.join(utils.DATA_DIR, "gpg-keys", "RPM-GPG-KEY-redhat-release")
# The SSL certificate of the https://cdn.redhat.com/ server
SSL_CERT_PATH = os.path.join(utils.DATA_DIR, "redhat-uep.pem")


LINK_KMODS_RH_POLICY = "https://access.redhat.com/third-party-software-support"
LINK_PREVENT_KMODS_FROM_LOADING = "https://access.redhat.com/solutions/41278"

#: Status code of an Action.
#:
#: When an action completes, it may have succeeded or failed.  We set the
#: `Action.status` attribute to one of the following values so that we know
#: what happened.  This mapping lets us use a symbolic name for the status
#: for readability but that is mapped to a specific integer for consumption
#: by other tools.
#:
#: .. note:: At the moment, we only make use of SUCCESS and ERROR.  Other
#:      statuses may be used in future releases as we refine this system
#:      and start to use it with console.redhat.com
#:
#: :SUCCESS: no problem.
#: :WARNING: the problem is just a warning displayed to the user. (unused,
#:      warnings are currently emitted directly from the Action)
#: :OVERRIDABLE: the error caused convert2rhel to fail but the user has
#:      the option to ignore the check in a future run.
#: :ERROR: the error caused convert2rhel to fail the conversion, but further
#:      tests can be run.
#: :FATAL: the error caused convert2rhel to stop immediately.
#:
#: .. warning:: Do not change the numeric value of these statuses once they
#:      have been in a public release as external tools may be depending on
#:      the value.
STATUS_CODE = {
    "SUCCESS": 0,
    "WARNING": 300,
    "OVERRIDABLE": 600,
    "ERROR": 900,
    "FATAL": 1200,
}


def _action_defaults_to_success(func):
    """
    Decorator to set default values for return values from this change.

    The way the Action class returns values is modelled on
    :class:`subprocess.Popen` in that all the data that is returned are set on
    the object's instance after :meth:`run` is called.  This decorator
    sets the functions to return values to success if the run() method did
    not explicitly return something different.
    """

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        return_value = func(self, *args, **kwargs)

        if self.status is None:
            self.status = STATUS_CODE["SUCCESS"]

        return return_value

    return wrapper


#: Used as a sentinel value for Action.set_result() method.
_NO_USER_VALUE = object()


@six.add_metaclass(abc.ABCMeta)
class Action:
    """Base class for writing a check."""

    # Once we can limit to Python3-3.3+ we can use this instead:
    # @property
    # @abc.abstractmethod
    # def id(self):
    @abc.abstractproperty  # pylint: disable=deprecated-decorator
    def id(self):
        """
        This should be replaced by a simple class attribute.
        It is a short string that uniquely identifies the Action.
        For instance::
            class Convert2rhelLatest(Action):
                id = "C2R_LATEST"

        `id` will be combined with `error_code` from the exception parameter
        list to create a unique key per error that can be used by other tools
        to tell what went wrong.
        """

    #: Override dependencies with a Sequence that has other :class:`Action`s
    #: that must be run before this one.
    dependencies = ()

    def __init__(self):
        """
        The attributes set here should be set when the run() method returns.

        They represent whether the Change succeeded or failed and if it failed,
        gives useful information to the user.
        """
        self.status = None
        self.message = None
        self.error_id = None

    @_action_defaults_to_success
    @abc.abstractmethod
    def run(self):
        """
        The method that performs the action.

        .. note:: This method should set :attr:`status`, :attr:`message`, and
            attr:`error_id` before returning.  The @action_defaults_to_success
            decorator takes care of setting a default success status but you
            can either add more information (for instance, a message to
            display to the user) or make additional changes to return an error
            instead.
        """

    def set_result(self, status=_NO_USER_VALUE, error_id=_NO_USER_VALUE, message=_NO_USER_VALUE):
        """
        Helper method that sets the resulting values for status, error_id and message.

        :param status: The status to be set.
        :type: status: str
        :param error_id: The error_id to identify the error.
        :type error_id: str
        :param message: The message to be set.
        :type message: str | None
        """
        if status != _NO_USER_VALUE:
            self.status = STATUS_CODE[status]

        if error_id != _NO_USER_VALUE:
            self.error_id = error_id

        if message != _NO_USER_VALUE:
            self.message = message


def get_actions(actions_path, prefix):
    """
    Determine the list of actions that exist at a path.

    :param actions_path: Filesystem path to the directory in which the
        Actions may live.
    :type actions_path: str
    :param prefix: Python dotted notation leading up to the Action.
    :type prefix: str
    :returns: A list of Action subclasses which existed at the given path.
    :rtype: list

    Sample usage::

        from convert2rhel.action import system_checks

        successful_actions = []
        failed_actions = []

        action_classes = get_actions(system_checks.__file__,
                                     system_checks.__name__ + ".")
        for action in action_classes:
            action.run()
            if action.status = STATUS_CODE["SUCCESS"]:
                successful_actions.append(action)
            else:
                failed_actions.append(action)
    """
    actions = []

    # In Python 3, this is a NamedTuple where m[1] == m.name and m[2] == m.ispkg
    modules = (m[1] for m in pkgutil.iter_modules(actions_path, prefix=prefix) if not m[2])
    modules = (importlib.import_module(m) for m in modules)

    for module in modules:
        objects = (getattr(module, obj_name) for obj_name in dir(module))
        action_classes = (
            obj for obj in objects if isinstance(obj, type) and issubclass(obj, Action) and obj is not Action
        )
        actions.extend(action_classes)

    return actions


def resolve_action_order(potential_actions, failed_actions):
    """
    Order the Actions according to the order in which they need to run.

    :arg potential_actions: Sequence of Actions which should be run.
    :arg failed_actions: A set of failed Actions.  resolve_action_order() does not modify this but
        does expect that its contents will be updated between iterations if there are more
        failures.
    :returns: A list of Actions sorted so that all dependent Actions are run before actions which
        depend on their output.
    :raises Exception: when it is impossible to satisfy a dependency in an Action.
    """
    previous_number_of_unresolved_actions = len(potential_actions)
    unresolved_actions = [action for action in potential_actions if action.dependencies]
    resolved_actions = [action for action in potential_actions if not action.dependencies]
    resolved_action_names = set(action.name for action in resolved_actions)

    while previous_number_of_unresolved_actions != len(unresolved_actions):
        previous_number_of_unresolved_actions = len(unresolved_actions)
        for action in unresolved_actions[:]:
            if all(d in resolved_action_names for d in action.dependencies):
                unresolved_actions.remove(action)
                resolved_action_names.add(action.__name__)
                resolved_actions.append(action)
                yield action

    if previous_number_of_unresolved_actions != 0:
        raise Exception(
            "Unresolvable Dependency in these actions: %s" % ", ".join(action.__name__ for action in unresolved_actions)
        )


def run_actions():
    potential_actions = get_actions(__path__, __name__)
    actions = resolve_action_order(potential_actions)
    for action in actions:
        try:
            action.run()
        except Exception as e:
            ### TODO: We need to keep a tree of actions according to dependencies so that we can run
            # all the actions which do not have failed dependencies.
            if hasattr(e.error_message):
                message = e.error_message
            else:
                message = str(e)
                message.append("\nException raised: %s" % e)
            logger.critical(message)
    # Each action will have one of the following statuses:
    # Pass
    # Fail
    # Could not run
    # Not Applicable
    # Actions and remediations:
    #   Remediations should live at the console integration level
    #   But convert2rhel needs to give enough information that the remediation can decide what to
    #   run
    #   For instance, if the action can fail for multiple reasons, the code needs to differentiate
    #   between which failure case caused this.
    #


def perform_pre_ponr_checks():
    """Late checks before ponr should be added here."""
    ensure_compatibility_of_kmods()
    validate_package_manager_transaction()


def ensure_compatibility_of_kmods():
    """Ensure that the host kernel modules are compatible with RHEL.

    :raises SystemExit: Interrupts the conversion because some kernel modules are not supported in RHEL.
    """
    host_kmods = get_loaded_kmods()
    rhel_supported_kmods = get_rhel_supported_kmods()
    unsupported_kmods = get_unsupported_kmods(host_kmods, rhel_supported_kmods)

    # Validate the best case first. If we don't have any unsupported_kmods, this means
    # that everything is compatible and good to go.
    if not unsupported_kmods:
        logger.debug("All loaded kernel modules are available in RHEL.")
    else:
        if "CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS" in os.environ:
            logger.warning(
                "Detected 'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS' environment variable."
                " We will continue the conversion with the following kernel modules unavailable in RHEL:\n"
                "{kmods}\n".format(kmods="\n".join(unsupported_kmods))
            )
        else:
            logger.critical(
                "The following loaded kernel modules are not available in RHEL:\n{0}\n"
                "Ensure you have updated the kernel to the latest available version and rebooted the system.\nIf this "
                "message persists, you can prevent the modules from loading by following {1} and rerun convert2rhel.\n"
                "Keeping them loaded could cause the system to malfunction after the conversion as they might not work "
                "properly with the RHEL kernel.\n"
                "To circumvent this check and accept the risk you can set environment variable "
                "'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS=1'.".format(
                    "\n".join(unsupported_kmods), LINK_PREVENT_KMODS_FROM_LOADING
                )
            )


def validate_package_manager_transaction():
    """Validate the package manager transaction is passing the tests."""
    logger.task("Prepare: Validate the %s transaction", pkgmanager.TYPE)
    transaction_handler = pkgmanager.create_transaction_handler()
    transaction_handler.run_transaction(
        validate_transaction=True,
    )


def get_loaded_kmods():
    """Get a set of kernel modules loaded on host.

    Each module we cut part of the path until the kernel release
    (i.e. /lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz ->
    kernel/lib/a.ko.xz) in order to be able to compare with RHEL
    kernel modules in case of different kernel release
    """
    logger.debug("Getting a list of loaded kernel modules.")
    lsmod_output, _ = run_subprocess(["lsmod"], print_output=False)
    modules = re.findall(r"^(\w+)\s.+$", lsmod_output, flags=re.MULTILINE)[1:]
    return set(
        _get_kmod_comparison_key(run_subprocess(["modinfo", "-F", "filename", module], print_output=False)[0])
        for module in modules
    )


def _get_kmod_comparison_key(path):
    """Create a comparison key from the kernel module abs path.

    Converts /lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz ->
    kernel/lib/a.ko.xz

    Why:
        The standard kernel modules are located under
        /lib/modules/{some kernel release}/.
        If we want to make sure that the kernel package is present
        on RHEL, we need to compare the full path, but because kernel release
        might be different, we compare the relative paths after kernel release.
    """
    return "/".join(path.strip().split("/")[4:])


def get_rhel_supported_kmods():
    """Return set of target RHEL supported kernel modules."""
    basecmd = [
        "repoquery",
        "--releasever=%s" % system_info.releasever,
    ]
    if system_info.version.major == 8:
        basecmd.append("--setopt=module_platform_id=platform:el8")

    for repoid in system_info.get_enabled_rhel_repos():
        basecmd.extend(("--repoid", repoid))

    cmd = basecmd[:]
    cmd.append("-f")
    cmd.append("/lib/modules/*.ko*")
    # Without the release package installed, dnf can't determine the modularity
    #   platform ID.
    # get output of a command to get all packages which are the source
    # of kmods
    kmod_pkgs_str, _ = run_subprocess(cmd, print_output=False)

    # from these packages we select only the latest one
    kmod_pkgs = get_most_recent_unique_kernel_pkgs(kmod_pkgs_str.rstrip("\n").split())
    if not kmod_pkgs:
        logger.debug("Output of the previous repoquery command:\n{0}".format(kmod_pkgs_str))
        logger.critical(
            "No packages containing kernel modules available in the enabled repositories ({0}).".format(
                ", ".join(system_info.get_enabled_rhel_repos())
            )
        )
    else:
        logger.info(
            "Comparing the loaded kernel modules with the modules available in the following RHEL"
            " kernel packages available in the enabled repositories:\n {0}".format("\n ".join(kmod_pkgs))
        )

    # querying obtained packages for files they produces
    cmd = basecmd[:]
    cmd.append("-l")
    cmd.extend(kmod_pkgs)
    rhel_kmods_str, _ = run_subprocess(cmd, print_output=False)

    return get_rhel_kmods_keys(rhel_kmods_str)


def get_most_recent_unique_kernel_pkgs(pkgs):
    """Return the most recent versions of all kernel packages.

    When we scan kernel modules provided by kernel packages
    it is expensive to check each kernel pkg. Since each new
    kernel pkg do not deprecate kernel modules we only select
    the most recent ones.

    .. note::
        All RHEL kmods packages starts with kernel* or kmod*

    For example, consider the following list of packages::

        list_of_pkgs = [
            'kernel-core-0:4.18.0-240.10.1.el8_3.x86_64',
            'kernel-core-0:4.19.0-240.10.1.el8_3.x86_64',
            'kmod-debug-core-0:4.18.0-240.10.1.el8_3.x86_64',
            'kmod-debug-core-0:4.18.0-245.10.1.el8_3.x86_64
        ]

    And when this function gets called with that same list of packages,
    we have the following output::

        result = get_most_recent_unique_kernel_pkgs(pkgs=list_of_pkgs)
        print(result)
        # (
        #   'kernel-core-0:4.19.0-240.10.1.el8_3.x86_64',
        #   'kmod-debug-core-0:4.18.0-245.10.1.el8_3.x86_64'
        # )

    :param pkgs: A list of package names to be analyzed.
    :type pkgs: list[str]
    :return: A tuple of packages name sorted and normalized
    :rtype: tuple[str]
    """

    pkgs_groups = itertools.groupby(sorted(pkgs), lambda pkg_name: pkg_name.split(":")[0])
    list_of_sorted_pkgs = []
    for distinct_kernel_pkgs in pkgs_groups:
        if distinct_kernel_pkgs[0].startswith(("kernel", "kmod")):
            list_of_sorted_pkgs.append(
                max(
                    distinct_kernel_pkgs[1],
                    key=cmp_to_key(compare_package_versions),
                )
            )

    return tuple(list_of_sorted_pkgs)


def get_rhel_kmods_keys(rhel_kmods_str):
    return set(
        _get_kmod_comparison_key(kmod_path)
        for kmod_path in filter(
            lambda path: path.endswith(("ko.xz", "ko")),
            rhel_kmods_str.rstrip("\n").split(),
        )
    )


def get_unsupported_kmods(host_kmods, rhel_supported_kmods):
    """Return a set of full paths to those installed kernel modules that are
    not available in RHEL repositories.

    Ignore certain kmods mentioned in the system configs. These kernel modules
    moved to kernel core, meaning that the functionality is retained and we
    would be incorrectly saying that the modules are not supported in RHEL.
    """
    unsupported_kmods_subpaths = host_kmods - rhel_supported_kmods - set(system_info.kmods_to_ignore)
    unsupported_kmods_full_paths = [
        "/lib/modules/{kver}/{kmod}".format(kver=system_info.booted_kernel, kmod=kmod)
        for kmod in unsupported_kmods_subpaths
    ]
    return unsupported_kmods_full_paths
