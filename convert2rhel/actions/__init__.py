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


import abc
import collections
import importlib
import itertools
import logging
import os
import os.path
import pkgutil
import re
import traceback

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
from convert2rhel.utils import ask_to_continue, format_sequence_as_message, get_file_content, run_subprocess


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
#:      warnings are currently emitted directly from the Action).
#: :SKIP: the action could not be run because a dependent Action failed.
#:      Actions should not return this. :func:`run_actions` will set this
#:      when it determines that an Action cannot be run due to dependencies
#:      having failed.
#: :OVERRIDABLE: the error caused convert2rhel to fail but the user has
#:      the option to ignore the check in a future run.
#: :ERROR: the error caused convert2rhel to fail the conversion, but further
#:      tests can be run.
#:
#: .. warning::
#:      * Do not change the numeric value of these statuses once they
#:        have been in a public release as external tools may be depending on
#:        the value.
#:      * Actions should not set a status to ``SKIP``.  The code which
#:        runs the Actions will set this.
STATUS_CODE = {
    "SUCCESS": 0,
    "WARNING": 51,
    "SKIP": 101,
    "OVERRIDABLE": 152,
    "ERROR": 202,
}

#: Maps status names back from an integer code.  Used for constructing log
#: messages and information for the user.
_STATUS_NAME_FROM_CODE = dict((value, key) for key, value in STATUS_CODE.items())


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


class ActionError(Exception):
    """Raised for errors related to the Action framework."""


class DependencyError(ActionError):
    """
    Raised when unresolved dependencies are encountered.

    Their are two non-standard attributes.

    :attr:`unresolved_actions` is a list of dependent actions which were
    not found.

    :attr:`resolved_actions` is a list of dependent actions which were
    found.
    """

    def __init__(self, *args, **kwargs):
        super(DependencyError, self).__init__(*args, **kwargs)
        self.unresolved_actions = kwargs.pop("unresolved_actions", [])
        self.resolved_actions = kwargs.pop("resolved_actions", [])


#: Contains Actions which have run, separated into categories by status.
#:
#: :param successes: Actions which have run successfully
#: :type: Sequence
#: :param failures: Actions which have failed
#: :type: Sequence
#: :param skips: Actions which have been skipped because a dependency failed
#: :type: Sequence
FinishedActions = collections.namedtuple("FinishedActions", ("successes", "failures", "skips"))


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

    #: Override dependencies with a Sequence that contains other
    #: :class:`Action`s :attr:`Action.id`s that must be run before this one.
    #: The :attr:`Action.id`s can be specified as string literals; you don't
    #: have to import the class to reference them in the Sequence.
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
        self._has_run = False

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
        if self._has_run:
            raise ActionError("Action %s has already run" % self.id)

        self._has_run = True

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

    :param actions_path: List of paths to the directory in which the
        Actions may live.
    :type actions_path: list
    :param prefix: Python dotted notation leading up to the Action.
    :type prefix: str
    :returns: Set of Action subclasses which existed at the given path.
    :rtype: set

    Sample usage::

        from convert2rhel.action import system_checks

        successful_actions = []
        failed_actions = []

        action_classes = get_actions(system_checks.__path__,
                                     system_checks.__name__ + ".")
        for action in resolve_action_order(action_classes):
            action.run()
            if action.status = STATUS_CODE["SUCCESS"]:
                successful_actions.append(action)
            else:
                failed_actions.append(action)

    .. seealso:: :func:`pkgutil.iter_modules`
        Consult :func:`pkgutil.iter_modules` for more information on
        actions_path and prefix which we pass verbatim to that function.
    """
    actions = set()

    # In Python 3, this is a NamedTuple where m[1] == m.name and m[2] == m.ispkg
    modules = (m[1] for m in pkgutil.iter_modules(actions_path, prefix=prefix) if not m[2])
    modules = (importlib.import_module(m) for m in modules)

    for module in modules:
        objects = (getattr(module, obj_name) for obj_name in dir(module))
        action_classes = (
            obj for obj in objects if isinstance(obj, type) and issubclass(obj, Action) and obj is not Action
        )
        actions.update(action_classes)

    return actions


class Stage:
    #: Private attribute to allow unittests to override this dir
    _actions_dir = "convert2rhel.actions.%s"

    def __init__(self, stage_name, task_header=None, next_stage=None):
        """
        Stages define a set of Actions which should be executed as a group.

        :param stage_name: Name of the stage.  This is also the name of the python
            package in ``convert2rhel.actions`` which contains all of the Actions
            in this Stage.
        :type stage_name: str
        :param task_header: A header that will be printed before the stage is run.
            If not given, this defaults to the stage_name.
        :type task_header: str
        :param next_stage: A Stage which will automatically be run after the
            Actions in this Stage have had a change to run.
        :type next_stage: str

        Stages are used for ordering only. This is different from
        Action.dependencies which are used for both ordering and to determine
        whether an Action can only run if a depended upon Action succeeded.

        A Stage specified in ``next_stage`` will be told about the Actions
        which have executed successfully and unsuccessfully in ths stage when
        it is run.
        """
        self.stage_name = stage_name
        self.task_header = task_header if task_header else stage_name
        self.next_stage = next_stage
        self._has_run = False

        python_package = importlib.import_module(self._actions_dir % self.stage_name)
        self.actions = get_actions(python_package.__path__, python_package.__name__ + ".")

    def check_dependencies(self, _previous_stage_actions=None):
        """
        Make sure dependencies of this Stage and previous stages are satisfied.

        :param _previous_stage_actions: Used internally when this function
            calls check_dependencies on the next_stage.  It holds the actions
            whose order has already been determined in this stage and previous
            stages.

        :raises DependencyError: when there is an unresolvable dependency in
            the set of actions.
        """
        # We want to throw an exception if one of the actions fails to resolve
        # its deps.  We don't care about the return value here.
        actions_so_far = list(resolve_action_order(self.actions, _previous_stage_actions))

        if self.next_stage:
            self.next_stage.check_dependencies(actions_so_far)

    def run(self, successes=None, failures=None, skips=None):
        """
        Run all the actions in Stage and other linked Stages.

        :keyword successes: Actions which have already run and succeeded.
        :type successes: Sequence
        :keyword failures: Actions which have already run and failed.
        :type failures: Sequence
        :keyword skips: Actions which have already run and have been skipped.
        :type skips: Sequence
        :return: 2-tuple consisting of two lists.  One with Actions that
            have succeeded and one of Actions that have failed.  These
            lists contain the Actions passed in via successes and failures
            in addition to any that were run in this :class`Stage`.

        :rtype: FinishedActions
        .. important:: Success is currently defined as an action whose status after
            running is WARNING or better (WARNING or SUCCESS) and
            failure as worse than WARNING (OVERRIDABLE, ERROR)
        """
        logger.task("Prepare: %s" % self.task_header)

        if self._has_run:
            raise ActionError("Stage %s has already run." % self.stage_name)
        self._has_run = True

        # Make a mutable copy of these parameters so we don't overwrite the caller's data.
        # If they weren't passed in, default to an empty list.
        successes = [] if successes is None else list(successes)
        failures = [] if failures is None else list(failures)
        skips = [] if skips is None else list(skips)

        # When testing for failed dependencies, we need the Action ids of failures and skips so
        # record those separately
        failed_action_ids = set()

        for action_class in resolve_action_order(
            self.actions, previously_resolved_actions=successes + failures + skips
        ):
            # Decide if we need to skip because deps have failed
            failed_deps = [d for d in action_class.dependencies if d in failed_action_ids]

            action = action_class()

            if failed_deps:
                to_be = "was"
                if len(failed_deps) > 1:
                    to_be = "were"
                message = "Skipped because %s %s not successful" % (format_sequence_as_message(failed_deps), to_be)

                action.set_result(status="SKIP", error_id="SKIP", message=message)
                skips.append(action)
                failed_action_ids.add(action.id)
                logger.error("Skipped %s. %s" % (action.id, message))
                continue

            # Run the Action
            try:
                action.run()
            except (Exception, SystemExit) as e:
                # Uncaught exceptions are handled by constructing a generic
                # failure message here that should be reported
                message = (
                    "Unhandled exception was caught: %s\n"
                    "Please file a bug at https://issues.redhat.com/ to have this"
                    " fixed or a specific error message added.\n"
                    "Traceback: %s" % (e, traceback.format_exc())
                )
                action.set_result(status="ERROR", error_id="UNEXPECTED_ERROR", message=message)

            # Categorize the results
            if action.status <= STATUS_CODE["WARNING"]:
                logger.info("%s has succeeded" % action.id)
                successes.append(action)

            if action.status > STATUS_CODE["WARNING"]:
                message = format_report_message(action.status, action.id, action.error_id, action.message)
                logger.error(message)
                failures.append(action)
                failed_action_ids.add(action.id)

        if self.next_stage:
            successes, failures, skips = self.next_stage.run(successes, failures, skips)

        return FinishedActions(successes, failures, skips)


def resolve_action_order(potential_actions, previously_resolved_actions=None):
    """
    Order the Actions according to the order in which they need to run.

    :param potential_actions: Sequence of Actions which we need to find the
        order of.
    :type potential_actions: Sequence
    :param previously_resolved_actions: Sequence of Actions which have already
        been resolved into dependency order.
    :type previously_resolved_actions: Sequence
    :raises DependencyError: when it is impossible to satisfy a dependency in
        an Action.
    :returns: Iterator of Actions sorted so that all dependent Actions are run
        before actions which depend on them.

    .. note::

        * The sort is stable but not predictable. The order will be the same
          as long as the Actions given has not changed but adding or
          subtracting Actions or dependencies can alter the order a lot.

        * The returned actions do not include ``previously_resolved_actions``.
          It is up to the caller to processs those before the actions returned
          by this function.
    """
    if previously_resolved_actions is None:
        previously_resolved_actions = []

    # Sort the potential actions before processing so that the dependency
    # order is stable. (Always yields the same order if the input and
    # algorithm has not changed)
    potential_actions = sorted(potential_actions, key=lambda action: action.id)

    # actions which have yet to be sorted
    unresolved_actions = []
    # ids of the actions which have already been sorted
    resolved_action_ids = set(action.id for action in previously_resolved_actions)

    for action in potential_actions:
        if not action.dependencies:
            # No dependencies so we can perform this immediately.
            resolved_action_ids.add(action.id)
            yield action
        else:
            # There are dependencies so we will have to make sure that its
            # dependencies have been been run first.
            unresolved_actions.append(action)

    # Add the length of all actions passed in together.  We decide whether
    # we're done sorting by comparing the previous unresolved actions to the
    # current number of unresolved_actions so we want this to be more than the
    # length of unresolved_actions to start with.
    previous_number_of_unresolved_actions = len(potential_actions) + len(previously_resolved_actions)

    # Keep trying to sort the actions until we haven't resolved any actions
    # since the last iteration of the while loop (each while loop examines
    # all of the unresolved actions once)
    while previous_number_of_unresolved_actions != len(unresolved_actions):
        previous_number_of_unresolved_actions = len(unresolved_actions)

        # Examine each action.  (Utilize a copy of unresolved_actions for the
        # loop since we add to unresolved_actions inside of the loop)]
        for action in unresolved_actions[:]:
            # We can only run the action if all of its dependencies have
            # previously been run
            if all(d in resolved_action_ids for d in action.dependencies):
                # Mark the action as being sorted by removing it from the
                # list of unresolved actions and adding its id to the set of
                # resolved actions.
                unresolved_actions.remove(action)
                resolved_action_ids.add(action.id)

                # Yield the action so that it will be run now.
                yield action

    # After exiting the while loop we know that we cannot run anymore actions
    # because there are no more whose dependencies have all been run.  If
    # there are any actions which are still unresolved at this point, it means
    # that some of them have unsatisfied dependencies.  This could mean the
    # dependencies aren't present, there was a typo in a dependency id, or
    # that there is a circular dependency that needs to be broken.
    if previous_number_of_unresolved_actions != 0:
        raise DependencyError(
            "Unsatisfied dependencies in these actions: %s" % ", ".join(action.id for action in unresolved_actions)
        )


def run_actions():
    pre_ponr_changes = Stage("pre_ponr_changes", "Making recoverable changes")
    system_checks = Stage("system_checks", "Check whether system is ready for conversion", pre_ponr_changes)

    try:
        system_checks.check_dependencies()
    except DependencyError as e:
        # We want to fail early if dependencies are not properly set.  This
        # way we should fail in testing before release.
        logger.critical("Some dependencies were set on Actions but not present in convert2rhel: %s" % e)

    results = system_checks.run()

    # Format results as a dictionary:
    # {"$Action_id": {"status": int,
    #                 "error_id": "$error_id",
    #                 "message": "" or "$message"},
    # }
    formatted_results = {}
    for action in itertools.chain(*results):
        formatted_results[action.id] = {"status": action.status, "error_id": action.error_id, "message": action.message}
    return formatted_results


def find_failed_actions(results):
    """
    Process results of run_actions for Actions which abort conversion.

    :param results: Results dictionary as returned by :func:`run_actions`
    :type results: Mapping
    :returns: List of actions which cause the conversion to stop. Empty list
        if there were no failures.
    :rtype: Sequence
    """
    failed_actions = [a[0] for a in results.items() if a[1]["status"] > STATUS_CODE["WARNING"]]

    return failed_actions


def format_report_message(status_code, action_id, error_id, message):
    """Helper function to format a message about each Action result.

    :param status_code: The status code that will be used in the template.
    :type status_code: int
    :param action_id: Action id for the message
    :type action_id: str
    :param error_id: Error id associated with the action
    :type error_id: str
    :param message: The message that was produced in the action
    :type message: str

    :return: The formatted message that will be logged to the user.
    :rtype: str
    """
    status_name = _STATUS_NAME_FROM_CODE[status_code]
    template = "({STATUS}) {ACTION_ID}"
    # `error_id` and `message` may not be present everytime, since it
    # can be empty (either by mistake, or, intended), we only want to
    # apply these fields if they are present, with a special mention to
    # `message`.
    if error_id:
        template += ".{ERROR_ID}"

    # Special case for `message` to not output empty message to the
    # user without message.
    if message:
        template += ": {MESSAGE}"
    else:
        template += ": [No further information given]"

    return template.format(
        STATUS=status_name,
        ACTION_ID=action_id,
        ERROR_ID=error_id,
        MESSAGE=message,
    )
