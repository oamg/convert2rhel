# Copyright: 2023, Red Hat
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
import pkgutil
import traceback

from functools import wraps

import six

from convert2rhel import utils


logger = logging.getLogger(__name__)


#: Status code of an Action.
#:
#: When an action completes, it may have succeeded or failed.  We set the
#: `Action.level` attribute to one of the following values so that we know
#: what happened.  This mapping lets us use a symbolic name for the level
#: for readability but that is mapped to a specific integer for consumption
#: by other tools.
#:
#: .. note:: At the moment, we only make use of SUCCESS and ERROR.  Other
#:      levels may be used in future releases as we refine this system
#:      and start to use it with console.redhat.com
#:
#: :SUCCESS: no problem.
#: :INFO: informational message to the user, no problem.
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
#:      * Do not change the numeric value of these levels once they
#:        have been in a public release as external tools may be depending on
#:        the value.
#:      * Actions should not set a level to ``SKIP``.  The code which
#:        runs the Actions will set this.
STATUS_CODE = {
    "SUCCESS": 0,
    "INFO": 25,
    "WARNING": 51,
    "SKIP": 101,
    "OVERRIDABLE": 152,
    "ERROR": 202,
}

#: Maps status names back from an integer code.  Used for constructing log
#: messages and information for the user.
_STATUS_NAME_FROM_CODE = dict((value, key) for key, value in STATUS_CODE.items())

#: When we print a report for the user to view, we want some explanation of
#: what the results mean
STATUS_HEADER = {
    0: "Success (No changes needed)",
    25: "Info (No changes needed)",
    51: "Warning (Review and fix if needed)",
    101: "Skip (Could not be checked due to other failures)",
    152: "Overridable (Review and either fix or ignore the failure)",
    202: "Error (Must fix before conversion)",
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

        if self.result is None:
            self.result = ActionResult(level="SUCCESS", id="SUCCESS")

        return return_value

    return wrapper


class ActionError(Exception):
    """Raised for errors related to the Action framework."""


class InvalidMessageError(ActionError):
    """Raised when invalid parameters are passed to set_result() or add_message()."""


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


#: Contains Actions which have run, separated into categories by level.
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
        self._has_run = False
        self._result = None
        self.messages = []

    @_action_defaults_to_success
    @abc.abstractmethod
    def run(self):
        """
        The method that performs the action.

        .. note:: This method should set self.result before returning.  The @action_defaults_to_success
            decorator takes care of setting a default success level but you
            can either add more information (for instance, a message to
            display to the user) or make additional changes to return an error
            instead.
        """
        if self._has_run:
            raise ActionError("Action %s has already run" % self.id)

        self._has_run = True

    @property
    def result(self):
        """
        Once the :class:`Action` is run, this holds the `result`.  The result is an :class:`ActionResult`
        which holds information of whether the Action succeeded or failed and why.
        """
        return self._result

    @result.setter
    def result(self, action_message):
        """
        Make sure the correct policy for result messages is used.
        """
        if not isinstance(action_message, ActionResult):
            raise TypeError()

        self._result = action_message

    def set_result(self, level, id, title="", description="", diagnosis="", remediations="", variables=None):
        """
        Helper method that sets the resulting values for level, id, title, description, diagnosis and remediations.

        :param id: The id to identify the result.
        :type id: str
        :param level: The status_code of the result.
        :type: level: str
        :param title: The title to be set.
        :type title: str
        :param description: The description of the result.
        :type description: str
        :param diagnosis: The outline of the issue found.
        :type diagnosis: str | None
        :param remediations: The steps that can be taken to resolve the issue.
        :type remediations: str | None
        :param variables: Variables to interpolate in other fields.
        :type variables: dict[str, str] | None
        """
        if level not in ("ERROR", "OVERRIDABLE", "SKIP", "SUCCESS"):
            raise KeyError("The level of result must be FAILURE, OVERRIDABLE, SKIP, or SUCCESS.")

        self.result = ActionResult(level, id, title, description, diagnosis, remediations, variables)

    def add_message(self, level, id, title="", description="", diagnosis="", remediations="", variables=None):
        """
        Helper method that adds a new informational message to display to the user.
        The passed in values for level, id and message of a warning or info log message are
        saved in an :class:`ActionMessage` which is appended to ``self.messages``

        :param id: The id to identify the message.
        :type id: str
        :param level: The level to be set.
        :type: level: str
        :param title: The title to be set.
        :type title: str
        :param description: The description of the message.
        :type description: str
        :param diagnosis: The outline of the issue found.
        :type diagnosis: str | None
        :param remediations: The steps that can be taken to resolve the issue.
        :type remediations: str | None
        :param variables: Variables to interpolate in other fields.
        :type variables: dict[str, str] | None
        """
        msg = ActionMessage(level, id, title, description, diagnosis, remediations, variables)
        self.messages.append(msg)


class ActionMessageBase:
    """
    Parent class for setting message and result variables and returning
    those values in a dictionary format

    :keyword id: The id to identify the message.
    :type id: str
    :keyword level: The level to be set, defaulting to SUCCESS.
    :type: level: str
    :keyword title: The title to be set.
    :type title: str
    :keyword description: The description to be set.
    :type description: str
    :keyword diagnosis: The diagnosis to be set.
    :type diagnosis: str | None
    :keyword remediations: The remediations to be set.
    :type remediations: str | None
    :keyword variables: The variables to be set.
    :type variables: dict[str,str] | None
    """

    def __init__(
        self, level="SUCCESS", id="SUCCESS", title="", description="", diagnosis="", remediations="", variables=None
    ):
        # Note, a common programming mistake to affect this base class is for
        # subclasses to pass None as a default value instead of empty string.
        # Not sure if we should be normalizng or if we should validate and
        # error but I'm going to obey "be liberal in what you accept and
        # conservative in what you emit" and normalize those cases for now.

        self.id = id or ""
        self.level = STATUS_CODE[level]
        self.title = title or ""
        self.description = description or ""
        self.diagnosis = diagnosis or ""
        self.remediations = remediations or ""

        if variables is None:
            variables = {}
        self.variables = variables

    def __eq__(self, other):
        if hash(self) == hash(other):
            return True
        return False

    def __hash__(self):
        return hash((self.level, self.id, self.title, self.description, self.diagnosis, self.remediations))

    def __repr__(self):
        return "%s(level=%s, id=%s, title=%s, description=%s, diagnosis=%s, remediations=%s, variables=%s)" % (
            self.__class__.__name__,
            _STATUS_NAME_FROM_CODE[self.level],
            self.id,
            self.title,
            self.description,
            self.diagnosis,
            self.remediations,
            self.variables,
        )

    def to_dict(self):
        """
        Returns a dictionary representation of the :class:`ActionMessageBase`.
        :returns: The attributes of :class:`ActionBase` expressed as a dictionary
        :rtype: dict
        """
        return {
            "id": self.id,
            "level": self.level,
            "title": self.title,
            "description": self.description,
            "diagnosis": self.diagnosis,
            "remediations": self.remediations,
            "variables": self.variables,
        }


class ActionMessage(ActionMessageBase):
    """
    A class that defines the contents and rules for messages set through :meth:`Action.add_message`.
    """

    def __init__(self, level="", id="", title="", description="", diagnosis="", remediations="", variables=None):
        if not (id and level and title and description):
            raise InvalidMessageError("Messages require id, level, title and description fields")

        # None of the result status codes are legal as a message.  So we error if any
        # of them were given here.
        if not (STATUS_CODE["SUCCESS"] < STATUS_CODE[level] < STATUS_CODE["SKIP"]):
            raise InvalidMessageError("Invalid level '%s', set for a non-result message" % level)

        super(ActionMessage, self).__init__(level, id, title, description, diagnosis, remediations, variables)


class ActionResult(ActionMessageBase):
    """
    A class that defines content and rules for messages set through :meth:`Action.set_result`.
    """

    def __init__(
        self, level="SUCCESS", id="SUCCESS", title="", description="", diagnosis="", remediations="", variables=None
    ):
        if level == "SUCCESS":
            if description or diagnosis or remediations:
                raise InvalidMessageError(
                    "Success results cannot have description, diagnosis or remediations fields set"
                )
        if not id:
            raise InvalidMessageError("Results require the id field")

        if STATUS_CODE[level] >= STATUS_CODE["SKIP"]:
            if not (level and title and description):
                # id is placed in the error message so it is less confusing for the user
                raise InvalidMessageError("Non-success results require level, title and description fields")

        elif STATUS_CODE["SUCCESS"] < STATUS_CODE[level] < STATUS_CODE["SKIP"]:
            raise InvalidMessageError(
                "Invalid level '%s', the level for result must be SKIP or more fatal or SUCCESS." % level
            )

        super(ActionResult, self).__init__(level, id, title, description, diagnosis, remediations, variables)


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
            if action.level == STATUS_CODE["SUCCESS"]:
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
        .. important:: Success is currently defined as an action whose level after
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
                diagnosis = "Skipped because %s %s not successful" % (
                    utils.format_sequence_as_message(failed_deps),
                    to_be,
                )

                action.set_result(
                    level="SKIP",
                    id="SKIP",
                    title="Skipped action",
                    description="This action was skipped due to another action failing.",
                    diagnosis=diagnosis,
                    remediations="Please ensure that the %s check passes so that this Action can evaluate your system"
                    % utils.format_sequence_as_message(failed_deps),
                )
                skips.append(action)
                failed_action_ids.add(action.id)
                logger.error("Skipped %s. %s" % (action.id, diagnosis))
                continue

            # Run the Action
            try:
                action.run()
            except (Exception, SystemExit) as e:
                # Uncaught exceptions are handled by constructing a generic
                # failure message here that should be reported
                description = (
                    "Unhandled exception was caught: %s\n"
                    "Please file a bug at https://issues.redhat.com/ to have this"
                    " fixed or a specific error message added.\n"
                    "Traceback: %s" % (e, traceback.format_exc())
                )
                action.set_result(
                    level="ERROR", id="UNEXPECTED_ERROR", title="Unhandled exception caught", description=description
                )

            # Categorize the results
            if action.result.level <= STATUS_CODE["WARNING"]:
                logger.info("%s has succeeded" % action.id)
                successes.append(action)

            if action.result.level > STATUS_CODE["WARNING"]:
                message = format_action_status_message(
                    action.result.level, action.id, action.result.id, action.result.to_dict()
                )
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

    # We have pre-sorted action by their id so that there is a stable sort order.
    # Now we have to sort them further so that dependencies are run before
    # the Actions which depend upon them.

    # Actions which have yet to be resolved.  A resolved Action has been sorted
    # into its final order and yielded to the caller.
    unresolved_actions = []
    # ids of the actions which have already been resolved
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
        # loop since we add to unresolved_actions inside of the loop)
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


def parse_action_results(results):
    """
    Parse and format action results

    .. note::
        # Format results as a dictionary:
        {
            "$Action_id": {
                "messages": [
                    {
                        "level": int,
                        "id": "$id",
                        "message": "" or "$message"
                    },
                ]
                "result": {
                    "level": int,
                    "id": "$id",
                    "message": "" or "$message"
                },
            },
        }

    :param results: Unformatted results given by the actions
    :type results: dict
    :return: Formatted dictionary with the results
    :rtype: dict[str, dict[str, list | dict]]
    """
    formatted_results = {}
    for action in itertools.chain(*results):
        msgs = [msg.to_dict() for msg in action.messages]
        formatted_results[action.id] = {"messages": msgs, "result": action.result.to_dict()}
    return formatted_results


def run_pre_actions():
    """
    Run all of the pre-ponr Actions.

    This function runs the Actions that occur before the Point of no Return.
    """
    # Stages are created in the opposite order that they are run in so that
    # each Stage can know about the Stage that comes after it (via the
    # next_stage parameter).
    #
    # When we call check_dependencies() or run() on the first Stage
    # (system_checks), it will operate on the first Stage and then recursively
    # call check_dependencies() or run() on the next_stage.
    pre_ponr_changes = Stage("pre_ponr_changes", "Making recoverable changes")
    system_checks = Stage("system_checks", "Check whether system is ready for conversion", next_stage=pre_ponr_changes)

    try:
        # Check dependencies are satisfied for system_checks and all subsequent
        # Stages.
        system_checks.check_dependencies()
    except DependencyError as e:
        # We want to fail early if dependencies are not properly set.  This
        # way we should fail in testing before release.
        logger.critical("Some dependencies were set on Actions but not present in convert2rhel: %s" % e)

    # Run the Actions in system_checks and all subsequent Stages.
    results = system_checks.run()

    return parse_action_results(results)


def run_post_actions():
    """
    Run all of the post-ponr Actions.

    This function runs the Actions that occur after the Point of no Return.
    """
    # Stages are created in the opposite order that they are run in so that
    # each Stage can know about the Stage that comes after it (via the
    # next_stage parameter).
    #
    # When we call check_dependencies() or run() on the first Stage
    # (system_checks), it will operate on the first Stage and then recursively
    # call check_dependencies() or run() on the next_stage.
    post_conversion = Stage("post_conversion", "Final modifications to the system")
    conversion = Stage("conversion", "Starting Conversion", next_stage=post_conversion)

    try:
        # Check dependencies are satisfied for system_checks and all subsequent
        # Stages.
        conversion.check_dependencies()
    except DependencyError as e:
        # We want to fail early if dependencies are not properly set.  This
        # way we should fail in testing before release.
        logger.critical("Some dependencies were set on Actions but not present in convert2rhel: %s" % e)

    # Run the Actions in system_checks and all subsequent Stages.
    results = conversion.run()

    return parse_action_results(results)


def level_for_raw_action_data(message):
    return message["result"]["level"]


def level_for_combined_action_data(message):
    return message["level"]


def find_actions_of_severity(results, severity, key):
    """
    Filter results from p:func:`run_actions` to include only results of ``severity`` or higher.

    :param results: Results dictionary as returned by :func:`run_actions`
    :type results: Mapping
    :param severity: The name of a ``STATUS_CODE`` for the severity to filter to.
    :param key: A key function to return the level from one entry in results
    :type key: callable
    :returns: List of actions which are at ``severity`` or higher result. Empty list
        if there were no failures.
    :rtype: Sequence

    Example::

        matched_actions = find_actions_of_severity(results, "SKIP")
        # matched_actions will contain all actions which were skipped
        # or failed while running.
    """
    matched_actions = [message for message in results.items() if key(message[1]) >= STATUS_CODE[severity]]
    return matched_actions


def format_action_status_message(status_code, action_id, id, result):
    """Helper function to format a message about each Action result.

    :param status_code: The status code that will be used in the template.
    :type status_code: int
    :param action_id: Action id for the message
    :type action_id: str
    :param id: Error id associated with the action
    :type id: str
    :param result: The result that was produced in the action
    :type result: dict[str, Any]

    :return: The formatted message that will be logged to the user.
    :rtype: str
    """
    level_name = _STATUS_NAME_FROM_CODE[status_code]
    template = "({LEVEL}) {ACTION_ID}::{ID} -"
    default_message = "N/A"

    # Success results doesn't need to have id, title or anything else. Instead,
    # we can output a simple message with the addition of the `No further
    # information given` and return earlier to skip the other conditionals
    # checks.
    if status_code == STATUS_CODE["SUCCESS"]:
        template += " {MESSAGE}"
        return template.format(ID=id, LEVEL=level_name, ACTION_ID=action_id, MESSAGE=default_message)

    title = result["title"]
    template += " {TITLE}\n"

    description = result["description"] if result["description"] else default_message
    template += " Description: {DESCRIPTION}\n"

    diagnosis = result["diagnosis"] if result["diagnosis"] else default_message
    template += " Diagnosis: {DIAGNOSIS}\n"

    remediations = result["remediations"] if result["remediations"] else default_message
    template += " Remediations: {REMEDIATIONS}\n"

    return template.format(
        LEVEL=level_name,
        ACTION_ID=action_id,
        ID=id,
        TITLE=title,
        DESCRIPTION=description,
        DIAGNOSIS=diagnosis,
        REMEDIATIONS=remediations,
    )
