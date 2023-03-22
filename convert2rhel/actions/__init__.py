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
CDN_URL = "https://cdn.redhat.com/content/public/convert2rhel/$releasever/$basearch/os/"
CONVERT2RHEL_REPO_CONTENT = """\
[convert2rhel]
name=Convert2RHEL Repository
baseurl=%s
gpgcheck=1
enabled=1
sslcacert=%s
gpgkey=file://%s""" % (
    CDN_URL,
    SSL_CERT_PATH,
    RPM_GPG_KEY_PATH,
)

PKG_NEVR = r"\b(\S+)-(?:([0-9]+):)?(\S+)-(\S+)\b"

LINK_KMODS_RH_POLICY = "https://access.redhat.com/third-party-software-support"
LINK_PREVENT_KMODS_FROM_LOADING = "https://access.redhat.com/solutions/41278"
# The kernel version stays the same throughout a RHEL major version
COMPATIBLE_KERNELS_VERS = {
    7: "3.10.0",
    8: "4.18.0",
}

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


def perform_system_checks():
    """Early checks after system facts should be added here."""
    check_custom_repos_are_valid()
    check_tainted_kmods()
    is_loaded_kernel_latest()


def perform_pre_ponr_checks():
    """Late checks before ponr should be added here."""
    ensure_compatibility_of_kmods()
    validate_package_manager_transaction()


def check_tainted_kmods():
    """Stop the conversion when a loaded tainted kernel module is detected.

    Tainted kmods ends with (...) in /proc/modules, for example:
        multipath 20480 0 - Live 0x0000000000000000
        linear 20480 0 - Live 0x0000000000000000
        system76_io 16384 0 - Live 0x0000000000000000 (OE)  <<<<<< Tainted
        system76_acpi 16384 0 - Live 0x0000000000000000 (OE) <<<<<< Tainted
    """
    logger.task("Prepare: Check if loaded kernel modules are not tainted")
    unsigned_modules, _ = run_subprocess(["grep", "(", "/proc/modules"])
    module_names = "\n  ".join([mod.split(" ")[0] for mod in unsigned_modules.splitlines()])
    if unsigned_modules:
        logger.critical(
            "Tainted kernel modules detected:\n  {0}\n"
            "Third-party components are not supported per our "
            "software support policy:\n {1}\n"
            "Prevent the modules from loading by following {2}"
            " and run convert2rhel again to continue with the conversion.".format(
                module_names, LINK_KMODS_RH_POLICY, LINK_PREVENT_KMODS_FROM_LOADING
            )
        )
    logger.info("No tainted kernel module is loaded.")


def check_custom_repos_are_valid():
    """To prevent failures past the PONR, make sure that the enabled custom repositories are valid.

    What is meant by valid:
    - YUM/DNF is able to find the repoids (to rule out a typo)
    - the repository "baseurl" is accessible and contains repository metadata
    """
    logger.task("Prepare: Check if --enablerepo repositories are accessible")

    if not tool_opts.no_rhsm:
        logger.info("Skipping the check of repositories due to the use of RHSM for the conversion.")
        return

    output, ret_code = call_yum_cmd(
        command="makecache",
        args=["-v", "--setopt=*.skip_if_unavailable=False"],
        print_output=False,
    )
    if ret_code != 0:
        logger.critical(
            "Unable to access the repositories passed through the --enablerepo option. "
            "For more details, see YUM/DNF output:\n{0}".format(output)
        )

    logger.debug("Output of the previous yum command:\n{0}".format(output))
    logger.info("The repositories passed through the --enablerepo option are all accessible.")


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


def _bad_kernel_version(kernel_release):
    """Return True if the booted kernel version does not correspond to the kernel version available in RHEL."""
    kernel_version = kernel_release.split("-")[0]
    try:
        incompatible_version = COMPATIBLE_KERNELS_VERS[system_info.version.major] != kernel_version
        if incompatible_version:
            logger.warning(
                "Booted kernel version '%s' does not correspond to the version "
                "'%s' available in RHEL %d"
                % (
                    kernel_version,
                    COMPATIBLE_KERNELS_VERS[system_info.version.major],
                    system_info.version.major,
                )
            )
        else:
            logger.debug(
                "Booted kernel version '%s' corresponds to the version available in RHEL %d"
                % (kernel_version, system_info.version.major)
            )
        return incompatible_version
    except KeyError:
        logger.debug("Unexpected OS major version. Expected: %r" % COMPATIBLE_KERNELS_VERS.keys())
        return True


def _bad_kernel_package_signature(kernel_release):
    """Return True if the booted kernel is not signed by the original OS vendor, i.e. it's a custom kernel."""
    vmlinuz_path = "/boot/vmlinuz-%s" % kernel_release

    kernel_pkg, return_code = run_subprocess(
        ["rpm", "-qf", "--qf", "%{VERSION}&%{RELEASE}&%{ARCH}&%{NAME}", vmlinuz_path], print_output=False
    )

    os_vendor = system_info.name.split()[0]
    if return_code == 1:
        logger.warning(
            "The booted kernel %s is not owned by any installed package."
            " It needs to be owned by a package signed by %s." % (vmlinuz_path, os_vendor)
        )

        return True

    version, release, arch, name = tuple(kernel_pkg.split("&"))
    logger.debug("Booted kernel package name: {0}".format(name))

    kernel_pkg_obj = get_installed_pkg_objects(name, version, release, arch)[0]
    kernel_pkg_gpg_fingerprint = get_pkg_fingerprint(kernel_pkg_obj)
    bad_signature = system_info.cfg_content["gpg_fingerprints"] != kernel_pkg_gpg_fingerprint

    # e.g. Oracle Linux Server -> Oracle or
    #      Oracle Linux Server -> CentOS Linux
    if bad_signature:
        logger.warning("Custom kernel detected. The booted kernel needs to be signed by %s." % os_vendor)
        return True

    logger.debug("The booted kernel is signed by %s." % os_vendor)
    return False


def _bad_kernel_substring(kernel_release):
    """Return True if the booted kernel release contains one of the strings that identify it as non-standard kernel."""
    bad_substring = any(bad_substring in kernel_release for bad_substring in BAD_KERNEL_RELEASE_SUBSTRINGS)
    if bad_substring:
        logger.debug(
            "The booted kernel '{0}' contains one of the disallowed "
            "substrings: {1}".format(kernel_release, BAD_KERNEL_RELEASE_SUBSTRINGS)
        )
        return True
    return False


def is_loaded_kernel_latest():
    """Check if the loaded kernel is behind or of the same version as in yum repos."""
    logger.task("Prepare: Check if the loaded kernel version is the most recent")

    if system_info.id == "oracle" and system_info.corresponds_to_rhel_eus_release():
        logger.info(
            "Skipping the check because there are no publicly available %s %d.%d repositories available."
            % (system_info.name, system_info.version.major, system_info.version.minor)
        )
        return

    cmd = [
        "repoquery",
        "--setopt=exclude=",
        "--quiet",
        "--qf",
        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
    ]

    reposdir = get_hardcoded_repofiles_dir()
    if reposdir and not system_info.has_internet_access:
        logger.warning("Skipping the check as no internet connection has been detected.")
        return

    # If the reposdir variable is not empty, meaning that it detected the
    # hardcoded repofiles, we should use that
    # instead of the system repositories located under /etc/yum.repos.d
    if reposdir:
        cmd.append("--setopt=reposdir=%s" % reposdir)

    # For Oracle/CentOS Linux 8 the `kernel` is just a meta package, instead,
    # we check for `kernel-core`. But 7 releases, the correct way to check is
    # using `kernel`.
    package_to_check = "kernel-core" if system_info.version.major >= 8 else "kernel"

    # Append the package name as the last item on the list
    cmd.append(package_to_check)

    # Look up for available kernel (or kernel-core) packages versions available
    # in different repositories using the `repoquery` command.  If convert2rhel
    # detects that it is running on a EUS system, then repoquery will use the
    # hardcoded repofiles available under `/usr/share/convert2rhel/repos`,
    # meaning that the tool will fetch only the latest kernels available for
    # that EUS version, and not the most updated version from other newer
    # versions.
    repoquery_output, return_code = run_subprocess(cmd, print_output=False)
    if return_code != 0:
        logger.debug("Got the following output: %s", repoquery_output)
        logger.warning(
            "Couldn't fetch the list of the most recent kernels available in "
            "the repositories. Skipping the loaded kernel check."
        )
        return

    packages = []
    # We are expecting a repoquery output which is similar to this:
    #   C2R     1671212820      3.10.0-1160.81.1.el7    updates
    # We need the `C2R` identifier to be present on the line so we can know for
    # sure that the line we are working with is a line that contains
    # relevant repoquery information to our check, otherwise, we just log the
    # information as debug and do nothing with it.
    for line in repoquery_output.split("\n"):
        if line.strip() and "C2R" in line:
            _, build_time, latest_kernel, repoid = tuple(str(line).split("\t"))
            packages.append((build_time, latest_kernel, repoid))
        else:
            # Mainly for debugging purposes to see what is happening if we got
            # anything else that does not have the C2R identifier at the start
            # of the line.
            logger.debug("Got a line without the C2R identifier: %s" % line)

    # If we don't have any packages, then something went wrong, we need to
    # decide wether to bail out or output a warning (only if the user used the
    # special environment variable for it.
    if not packages:
        unsupported_skip = os.environ.get("CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK", None)
        if not unsupported_skip:
            logger.critical(
                "Could not find any %s from repositories to compare against the loaded kernel.\n"
                "Please, check if you have any vendor repositories enabled to proceed with the conversion.\n"
                "If you wish to ignore this message, set the environment variable "
                "'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK' to 1." % package_to_check
            )

        logger.warning(
            "Detected 'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK' environment variable, we will skip "
            "the %s comparison.\n"
            "Beware, this could leave your system in a broken state. " % package_to_check
        )
        return

    packages.sort(key=lambda x: x[0], reverse=True)
    _, latest_kernel, repoid = packages[0]

    uname_output, _ = run_subprocess(["uname", "-r"], print_output=False)
    loaded_kernel = uname_output.rsplit(".", 1)[0]
    # append the package name to loaded_kernel and latest_kernel so they can be properly processed by
    # compare_package_versions()
    latest_kernel_pkg = "%s-%s" % (package_to_check, latest_kernel)
    loaded_kernel_pkg = "%s-%s" % (package_to_check, loaded_kernel)
    match = compare_package_versions(latest_kernel_pkg, loaded_kernel_pkg)

    if match != 0:
        repos_message = (
            "in the enabled system repositories"
            if not reposdir
            else "in repositories defined in the %s folder" % reposdir
        )
        logger.critical(
            "The version of the loaded kernel is different from the latest version %s.\n"
            " Latest kernel version available in %s: %s\n"
            " Loaded kernel version: %s\n\n"
            "To proceed with the conversion, update the kernel version by executing the following step:\n\n"
            "1. yum install %s-%s -y\n"
            "2. reboot" % (repos_message, repoid, latest_kernel, loaded_kernel, package_to_check, latest_kernel)
        )

    logger.info("The currently loaded kernel is at the latest version.")
