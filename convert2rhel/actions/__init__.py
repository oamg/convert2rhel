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
    # TODO(abadger): Fix this later
    actions = resolve_action_order(potential_actions, None)
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
