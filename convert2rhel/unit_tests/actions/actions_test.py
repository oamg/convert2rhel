# -*- coding: utf-8 -*-
#
# Copyright(C) 2018 Red Hat, Inc.
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

import os.path
import re

from collections import defaultdict

import pytest
import six


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import actions
from convert2rhel.actions import STATUS_CODE, ActionMessage, ActionMessageBase, ActionResult, InvalidMessageError
from convert2rhel.main import level_for_raw_action_data


class _ActionForTesting(actions.Action):
    """Fake Action class where we can set all of the attributes as we like."""

    id = None

    def __init__(self, **kwargs):
        super(_ActionForTesting, self).__init__()

        for attr_name, attr_value in kwargs.items():
            setattr(self, attr_name, attr_value)

    def run(self):
        super(_ActionForTesting, self).run()
        pass


class TestAction:
    """Tests across all of the Actions we ship."""

    @pytest.mark.parametrize(
        ("set_result_params", "expected"),
        (
            # Set one result field
            (
                dict(level="SUCCESS", id="SUCCESS"),
                dict(level="SUCCESS", id="SUCCESS", title=None, description=None, diagnosis=None, remediation=None),
            ),
            # Set all result fields
            (
                dict(
                    level="ERROR",
                    id="ERRORCASE",
                    title="Problem detected",
                    description="problem",
                    diagnosis="detected",
                    remediation="move on",
                ),
                dict(
                    level="ERROR",
                    id="ERRORCASE",
                    title="Problem detected",
                    description="problem",
                    diagnosis="detected",
                    remediation="move on",
                ),
            ),
        ),
    )
    def test_set_results_successful(self, set_result_params, expected):
        action = _ActionForTesting(id="TestAction")
        level = set_result_params.pop("level")
        action.set_result(level, **set_result_params)
        action.run()

        assert action.result.level == STATUS_CODE[expected["level"]]

        assert action.result.id == expected["id"]
        assert action.result.title == expected["title"]
        assert action.result.description == expected["description"]
        assert action.result.diagnosis == expected["diagnosis"]
        assert action.result.remediation == expected["remediation"]

    @pytest.mark.parametrize(
        ("level", "id"),
        (
            ("FOOBAR", "FOOBAR"),
            (actions.STATUS_CODE["ERROR"], "ERROR_ID"),
        ),
    )
    def test_set_results_bad_level(self, level, id):
        action = _ActionForTesting(id="TestAction")

        with pytest.raises(KeyError):
            action.set_result(level=level, id=id)

    def test_no_duplicate_ids(self):
        """Test that each Action has its own unique id."""
        computed_actions = actions.get_actions(actions.__path__, actions.__name__ + ".")

        action_id_locations = defaultdict(list)
        for action in computed_actions:
            action_id_locations[action.id].append(str(action))

        dupe_actions = []
        for action_id, locations in action_id_locations.items():
            if len(locations) > 1:
                dupe_actions.append("%s is present in more than one location: %s" % (action_id, ", ".join(locations)))

        assert not dupe_actions, "\n".join(dupe_actions)

    def test_actions_cannot_be_run_twice(self):
        """Test that an Action can only be run once."""
        action = _ActionForTesting(id="TestAction")
        action.run()

        with pytest.raises(actions.ActionError, match="Action TestAction has already run"):
            action.run()

    def test_add_message(self):
        """Test that add_message formats messages correctly"""
        action = _ActionForTesting(id="TestAction")
        action.add_message(
            level="WARNING",
            id="WARNING_ID",
            title="warning message 1",
            description="action warning",
            diagnosis="user warning",
            remediation="move on",
        )
        action.add_message(
            level="WARNING",
            id="WARNING_ID",
            title="warning message 2",
            description="action warning",
            diagnosis="user warning",
            remediation="move on",
        )
        action.add_message(
            level="INFO",
            id="INFO_ID",
            title="info message 1",
            description="action info",
            diagnosis="user info",
            remediation="move on",
        )
        action.add_message(
            level="INFO",
            id="INFO_ID",
            title="info message 2",
            description="action info",
            diagnosis="user info",
            remediation="move on",
        )
        actual_messages = []
        for msg in action.messages:
            actual_messages.append(msg.to_dict())
        assert actual_messages == [
            {
                "level": STATUS_CODE["WARNING"],
                "id": "WARNING_ID",
                "title": "warning message 1",
                "description": "action warning",
                "diagnosis": "user warning",
                "remediation": "move on",
                "variables": {},
            },
            {
                "level": STATUS_CODE["WARNING"],
                "id": "WARNING_ID",
                "title": "warning message 2",
                "description": "action warning",
                "diagnosis": "user warning",
                "remediation": "move on",
                "variables": {},
            },
            {
                "level": STATUS_CODE["INFO"],
                "id": "INFO_ID",
                "title": "info message 1",
                "description": "action info",
                "diagnosis": "user info",
                "remediation": "move on",
                "variables": {},
            },
            {
                "level": STATUS_CODE["INFO"],
                "id": "INFO_ID",
                "title": "info message 2",
                "description": "action info",
                "diagnosis": "user info",
                "remediation": "move on",
                "variables": {},
            },
        ]


class TestGetActions:
    ACTION_CLASS_DEFINITION_RE = re.compile(r"^class .+\([^)]*Action\):$", re.MULTILINE)

    def test_get_actions_smoketest(self):
        """Test that there are no errors loading the Actions we ship."""
        computed_actions = []

        # Is this method of finding how many Action plugins we ship too hacky?
        filesystem_detected_actions_count = 0
        for rootdir, dirnames, filenames in os.walk(os.path.dirname(actions.__file__)):
            for directory in dirnames:
                # Add to the actions that the production code finds here as it is non-recursive
                computed_actions.extend(
                    actions.get_actions([os.path.join(rootdir, directory)], "%s.%s." % (actions.__name__, directory))
                )

            for filename in (os.path.join(rootdir, filename) for filename in filenames):
                if filename.endswith(".py") and not filename.endswith("/__init__.py"):
                    with open(filename) as f:
                        action_classes = self.ACTION_CLASS_DEFINITION_RE.findall(f.read())
                        filesystem_detected_actions_count += len(action_classes)

        assert len(computed_actions) == filesystem_detected_actions_count

    def test_get_actions_no_dupes(self):
        """Test that there are no duplicates in the list of returned Actions."""
        computed_actions = actions.get_actions(actions.__path__, actions.__name__ + ".")

        assert len(computed_actions) == len(frozenset(computed_actions))

    def test_no_actions(self, tmpdir):
        """No Actions returns an empty list."""
        # We need to make sure this returns an empty set, not just false-y
        assert (
            actions.get_actions([str(tmpdir)], "tmp.")
            == set()  # pylint: disable=use-implicit-booleaness-not-comparison
        )

    @pytest.mark.parametrize(
        (
            "test_dir_name",
            "expected_action_names",
        ),
        (
            ("aliased_action_name", ["RealTest"]),
            ("extraneous_files", ["RealTest"]),
            ("ignore__init__", ["RealTest"]),
            ("multiple_actions_one_file", ["RealTest", "SecondTest"]),
            ("multiple_actions_multiple_files", ["TestAction1", "TestAction2"]),
            ("not_action_itself", ["RealTest", "OtherTest"]),
            ("only_subclasses_of_action", ["RealTest"]),
        ),
    )
    def test_found_actions(self, sys_path, test_dir_name, expected_action_names):
        """Set of Actions that we have generated is found."""
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        sys_path.insert(0, data_dir)
        test_data = os.path.join(data_dir, test_dir_name)
        computed_action_names = sorted(
            m.__name__
            for m in actions.get_actions([test_data], "convert2rhel.unit_tests.actions.data.%s." % test_dir_name)
        )
        assert computed_action_names == sorted(expected_action_names)


@pytest.fixture
def stage_actions(monkeypatch):
    monkeypatch.setattr(actions.Stage, "_actions_dir", "convert2rhel.unit_tests.actions.data.stage_tests.%s")


class TestStage:
    #
    # Tests that the Stage is crated successfully
    #
    def test_init(self, stage_actions):

        stage1 = actions.Stage("good_deps1", "Task Header")
        stage2 = actions.Stage("good_deps_failed_actions", "Task Header2", stage1)

        assert stage1.stage_name == "good_deps1"
        assert stage1.task_header == "Task Header"
        assert stage1.next_stage is None
        assert sorted(a.id for a in stage1.actions) == sorted(["REALTEST", "SECONDTEST", "THIRDTEST", "FOURTHTEST"])

        assert stage2.stage_name == "good_deps_failed_actions"
        assert stage2.task_header == "Task Header2"
        assert stage2.next_stage is stage1
        assert sorted(a.id for a in stage2.actions) == sorted(["ATEST", "BTEST"])

    #
    # Tests that check_dependencies finds dependency problems and no false positives
    #
    @pytest.mark.parametrize(
        ("stage_dirs",),
        (
            (("good_deps1",),),
            (("good_deps1", "good_deps_failed_actions"),),
            (("good_deps_failed_actions", "good_deps1"),),
            (("deps_on_1", "good_deps1"),),
        ),
    )
    def test_check_dependencies_pass(self, stage_actions, stage_dirs):
        stage = None
        for stage_dir in stage_dirs:
            stage = actions.Stage(stage_dir, next_stage=stage)

        stage.check_dependencies()

    @pytest.mark.parametrize(
        ("stage_dirs",),
        (
            (("bad_deps1",),),
            (("bad_deps1", "good_deps_failed_actions"),),
            (("good_deps_failed_actions", "bad_deps1"),),
            (("good_deps1", "deps_on_1"),),
            (("deps_on_1", "good_deps_failed_actions"),),
            (("deps_on_1",),),
        ),
    )
    def test_check_dependencies_fail(self, stage_actions, stage_dirs):
        stage = None
        for stage_dir in stage_dirs:
            stage = actions.Stage(stage_dir, next_stage=stage)

        with pytest.raises(actions.DependencyError):
            stage.check_dependencies()

    def test_check_dependencies_real_actions(self):
        """Check the Actions we ship have no broken deps."""
        pre_ponr_changes = actions.Stage("pre_ponr_changes", "changes")
        system_checks = actions.Stage("system_checks", "checks", pre_ponr_changes)

        system_checks.check_dependencies()

    #
    # Test that Stage.run() works as expected
    #
    @pytest.mark.parametrize(
        ("stage_dirs", "expected"),
        (
            # Single Stages
            (
                ("good_deps1",),
                (("REALTEST", "SECONDTEST", "THIRDTEST", "FOURTHTEST"), (), ()),
            ),
            # Test that all action levels are categorized correctly
            (
                ("all_status_actions",),
                (
                    ("SUCCESSTEST", "WARNINGTEST"),
                    ("ERRORTEST", "OVERRIDABLETEST"),
                    ("SKIPSINGLETEST", "SKIPMULTIPLETEST"),
                ),
            ),
            # Test that exceptions inside of Actions are detected as errors
            (
                ("action_exceptions",),
                (("SUCCESSTEST",), ("DIVIDEBYZEROTEST", "LOGCRITICALTEST"), ()),
            ),
            # Multiple Stages
            (
                ("deps_on_1", "good_deps1"),
                (("REALTEST", "SECONDTEST", "THIRDTEST", "FOURTHTEST", "TESTI", "TESTII"), (), ()),
            ),
        ),
    )
    def test_run(self, stage_actions, stage_dirs, expected):
        stage = None
        for stage_dir in stage_dirs:
            stage = actions.Stage(stage_dir, next_stage=stage)

        actual = stage.run()

        # Assert that the success, fail, and skipped lists are the same
        assert sorted(action.id for action in actual.successes) == sorted(expected[0])
        assert sorted(action.id for action in actual.failures) == sorted(expected[1])
        assert sorted(action.id for action in actual.skips) == sorted(expected[2])

    def test_stages_cannot_be_run_twice(self, stage_actions):
        """Test that an Action can only be run once."""
        stage = actions.Stage("good_deps1")
        stage.run()

        with pytest.raises(actions.ActionError, match="Stage good_deps1 has already run"):
            stage.run()


class TestResolveActionOrder:
    @pytest.mark.parametrize(
        ("potential_actions", "ordered_result"),
        (
            ([], []),
            ([_ActionForTesting(id="One")], ["One"]),
            (
                [_ActionForTesting(id="One"), _ActionForTesting(id="Two", dependencies=("One",))],
                ["One", "Two"],
            ),
            (
                [_ActionForTesting(id="Two"), _ActionForTesting(id="One", dependencies=("Two",))],
                ["Two", "One"],
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("One",)),
                    _ActionForTesting(id="Three", dependencies=("Two",)),
                    _ActionForTesting(id="Four", dependencies=("Three",)),
                ],
                ["One", "Two", "Three", "Four"],
            ),
            # Multiple dependencies (Slight differences in order to show
            # that order of deps and Actions doesn't matter).  The sort is
            # still stable.
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("One",)),
                    _ActionForTesting(
                        id="Three",
                        dependencies=(
                            "Two",
                            "One",
                        ),
                    ),
                    _ActionForTesting(id="Four", dependencies=("Three",)),
                ],
                ["One", "Two", "Three", "Four"],
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("One",)),
                    _ActionForTesting(id="Three", dependencies=("Two",)),
                    _ActionForTesting(
                        id="Four",
                        dependencies=(
                            "One",
                            "Three",
                        ),
                    ),
                ],
                ["One", "Two", "Three", "Four"],
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("One",)),
                    _ActionForTesting(id="Three", dependencies=("Two",)),
                    _ActionForTesting(
                        id="Four",
                        dependencies=(
                            "Three",
                            "One",
                        ),
                    ),
                ],
                ["One", "Two", "Three", "Four"],
            ),
        ),
    )
    def test_one_solution(self, potential_actions, ordered_result):
        """Resolve order when only one solutions satisfies dependencies."""
        computed_actions = actions.resolve_action_order(potential_actions)
        computed_action_ids = [action.id for action in computed_actions]
        assert computed_action_ids == ordered_result

    # Note: Each of these sets of Actions have multiple solutions but
    # the stable sort assurance should guarantee that the order is only a
    # single one of these.  The alternates are commented out to show they
    # aren't really wrong, but we expect that the stable sort will mean we
    # always get the order that is uncommented.  If the algorithm changes
    # between releases, we may want to allow any of the alternates as well.
    @pytest.mark.parametrize(
        ("potential_actions", "possible_orders"),
        (
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("One",)),
                    _ActionForTesting(id="Three", dependencies=("One",)),
                    _ActionForTesting(id="Four", dependencies=("Three",)),
                ],
                (
                    # ["One", "Two", "Three", "Four"],
                    ["One", "Three", "Two", "Four"],
                ),
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("One",)),
                    _ActionForTesting(id="Three", dependencies=("One",)),
                    _ActionForTesting(id="Four", dependencies=("One",)),
                ],
                (
                    # ["One", "Two", "Three", "Four"],
                    # ["One", "Two", "Four", "Three"],
                    # ["One", "Three", "Two", "Four"],
                    # ["One", "Three", "Four", "Two"],
                    # ["One", "Four", "Two", "Three"],
                    ["One", "Four", "Three", "Two"],
                ),
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two"),
                    _ActionForTesting(id="Three", dependencies=("One",)),
                    _ActionForTesting(id="Four", dependencies=("Two",)),
                ],
                (
                    # ["One", "Two", "Three", "Four"],
                    ["One", "Two", "Four", "Three"],
                    # ["One", "Three", "Two", "Four"],
                    # ["Two", "One", "Three", "Four"],
                    # ["Two", "One", "Four", "Three"],
                    # ["Two", "Four", "One", "Three"],
                ),
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(
                        id="Two",
                        dependencies=(
                            "One",
                            "Three",
                        ),
                    ),
                    _ActionForTesting(id="Three", dependencies=("One",)),
                    _ActionForTesting(id="Four", dependencies=("Three",)),
                ],
                (
                    ["One", "Three", "Two", "Four"],
                    # ["One", "Three", "Four", "Two"],
                ),
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two"),
                    _ActionForTesting(id="Three"),
                ],
                (
                    # ["One", "Two", "Three"],
                    ["One", "Three", "Two"],
                    # ["Two", "One", "Three"],
                    # ["Two", "Three", "One"],
                    # ["Three", "One", "Two"],
                    # ["Three", "Two", "One"],
                ),
            ),
        ),
    )
    def test_multiple_solutions(self, potential_actions, possible_orders):
        """
        When multiple solutions exist, the code chooses a single correct solution.

        This test both checks that the order is correct and that the sort is
        stable (it doesn't change between runs or on different distributionss).
        """
        computed_actions = actions.resolve_action_order(potential_actions)
        computed_action_ids = [action.id for action in computed_actions]
        assert computed_action_ids in possible_orders

    @pytest.mark.parametrize(
        ("potential_actions",),
        (
            # Dependencies that don't exist
            (
                [
                    _ActionForTesting(id="One", dependencies=("Unknown",)),
                ],
            ),
            (
                [
                    _ActionForTesting(id="One", dependencies=("Unknown",)),
                    _ActionForTesting(id="Two", dependencies=("One",)),
                ],
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("One",)),
                    _ActionForTesting(id="Two", dependencies=("Unknown",)),
                ],
            ),
            # Circular deps
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("Three",)),
                    _ActionForTesting(id="Three", dependencies=("Two",)),
                ],
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("Three",)),
                    _ActionForTesting(id="Three", dependencies=("Four",)),
                    _ActionForTesting(id="Four", dependencies=("Two",)),
                ],
            ),
            (
                [
                    _ActionForTesting(id="One", dependencies=("Three",)),
                    _ActionForTesting(id="Two", dependencies=("Three",)),
                    _ActionForTesting(id="Three", dependencies=("Four",)),
                    _ActionForTesting(id="Four", dependencies=("One",)),
                ],
            ),
        ),
    )
    def test_no_solutions(self, potential_actions):
        """All of these have unsatisfied dependencies."""
        with pytest.raises(actions.DependencyError):
            list(actions.resolve_action_order(potential_actions))

    @pytest.mark.parametrize(
        ("potential", "previous", "ordered_result"),
        (
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(
                        id="Two",
                        dependencies=(
                            "One",
                            "Three",
                        ),
                    ),
                    _ActionForTesting(id="Three", dependencies=("One",)),
                    _ActionForTesting(id="Four", dependencies=("Two",)),
                ],
                [
                    _ActionForTesting(id="Zero"),
                ],
                ["One", "Three", "Two", "Four"],
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("Zero",)),
                    _ActionForTesting(id="Three", dependencies=("One", "Two")),
                    _ActionForTesting(id="Four", dependencies=("Three",)),
                ],
                [
                    _ActionForTesting(id="Zero"),
                ],
                ["One", "Two", "Three", "Four"],
                # ["Two", "One", "Three", "Four"],
            ),
            (
                [
                    _ActionForTesting(id="One"),
                    _ActionForTesting(id="Two", dependencies=("One",)),
                ],
                [
                    _ActionForTesting(id="Zero"),
                    _ActionForTesting(id="Three"),
                    _ActionForTesting(id="Zed"),
                ],
                ["One", "Two"],
            ),
            (
                [
                    _ActionForTesting(id="One", dependencies=("Zero",)),
                    _ActionForTesting(
                        id="Two",
                        dependencies=(
                            "Zero",
                            "One",
                        ),
                    ),
                ],
                [
                    _ActionForTesting(id="Zero"),
                ],
                ["One", "Two"],
            ),
        ),
    )
    def test_with_previously_resolved_actions(self, potential, previous, ordered_result):
        computed_actions = actions.resolve_action_order(potential, previously_resolved_actions=previous)

        computed_action_ids = [action.id for action in computed_actions]
        assert computed_action_ids == ordered_result

    @pytest.mark.parametrize(
        ("potential", "previous"),
        (
            (
                [_ActionForTesting(id="One", dependencies=("Unknown",))],
                [
                    _ActionForTesting(id="Zero"),
                ],
            ),
            (
                [_ActionForTesting(id="One"), _ActionForTesting(id="Four", dependencies=("Unknown",))],
                [
                    _ActionForTesting(id="Zero"),
                ],
            ),
        ),
    )
    def test_with_previously_resolved_actions_no_solutions(self, potential, previous):
        with pytest.raises(actions.DependencyError):
            list(actions.resolve_action_order(potential, previous))


class TestRunActions:
    @pytest.mark.parametrize(
        ("action_results", "expected"),
        (
            # Only successes
            (
                actions.FinishedActions([], [], []),
                {},
            ),
            (
                actions.FinishedActions(
                    [
                        _ActionForTesting(id="One", messages=[], result=ActionResult(level="SUCCESS", id="SUCCESS")),
                    ],
                    [],
                    [],
                ),
                {
                    "One": dict(
                        messages=[],
                        result=dict(
                            level=STATUS_CODE["SUCCESS"],
                            id="SUCCESS",
                            title="",
                            description="",
                            diagnosis="",
                            remediation="",
                            variables={},
                        ),
                    )
                },
            ),
            (
                actions.FinishedActions(
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[],
                            result=ActionResult(level="SUCCESS", id="SUCCESS"),
                            dependencies=("One",),
                        ),
                        _ActionForTesting(
                            id="Two",
                            messages=[],
                            result=ActionResult(level="SUCCESS", id="SUCCESS"),
                            dependencies=(
                                "One",
                                "Two",
                            ),
                        ),
                    ],
                    [],
                    [],
                ),
                {
                    "One": dict(
                        messages=[],
                        result=dict(
                            level=STATUS_CODE["SUCCESS"],
                            id="SUCCESS",
                            title="",
                            description="",
                            diagnosis="",
                            remediation="",
                            variables={},
                        ),
                    ),
                    "Two": dict(
                        messages=[],
                        result=dict(
                            level=STATUS_CODE["SUCCESS"],
                            id="SUCCESS",
                            title="",
                            description="",
                            diagnosis="",
                            remediation="",
                            variables={},
                        ),
                    ),
                },
            ),
            # Single Failures
            (
                actions.FinishedActions(
                    [],
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[],
                            result=ActionResult(
                                level="ERROR",
                                id="SOME_ERROR",
                                title="Error",
                                description="Action error",
                                diagnosis="User error",
                                remediation="move on",
                            ),
                        ),
                    ],
                    [],
                ),
                {
                    "One": dict(
                        messages=[],
                        result=dict(
                            level=STATUS_CODE["ERROR"],
                            id="SOME_ERROR",
                            title="Error",
                            description="Action error",
                            diagnosis="User error",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                },
            ),
            (
                actions.FinishedActions(
                    [],
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[],
                            result=ActionResult(
                                level="OVERRIDABLE",
                                id="SOME_ERROR",
                                title="Overridable",
                                description="Action overridable",
                                diagnosis="User overridable",
                                remediation="move on",
                            ),
                        ),
                    ],
                    [],
                ),
                {
                    "One": dict(
                        messages=[],
                        result=dict(
                            level=STATUS_CODE["OVERRIDABLE"],
                            id="SOME_ERROR",
                            title="Overridable",
                            description="Action overridable",
                            diagnosis="User overridable",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                },
            ),
            (
                actions.FinishedActions(
                    [],
                    [],
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[],
                            result=ActionResult(
                                level="SKIP",
                                id="SOME_ERROR",
                                title="Skip",
                                description="Action skip",
                                diagnosis="User skip",
                                remediation="move on",
                            ),
                        ),
                    ],
                ),
                {
                    "One": dict(
                        messages=[],
                        result=dict(
                            level=STATUS_CODE["SKIP"],
                            id="SOME_ERROR",
                            title="Skip",
                            description="Action skip",
                            diagnosis="User skip",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                },
            ),
            # Mixture of failures and successes.
            (
                actions.FinishedActions(
                    [
                        _ActionForTesting(id="Three", messages=[], result=ActionResult(level="SUCCESS", id="SUCCESS")),
                    ],
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[],
                            result=ActionResult(
                                level="ERROR",
                                id="ERROR_ID",
                                title="Error",
                                description="Action error",
                                diagnosis="User error",
                                remediation="move on",
                            ),
                        ),
                    ],
                    [
                        _ActionForTesting(
                            id="Two",
                            messages=[],
                            result=ActionResult(
                                level="SKIP",
                                id="SKIP_ID",
                                title="Skip",
                                description="Action skip",
                                diagnosis="User skip",
                                remediation="move on",
                            ),
                        ),
                    ],
                ),
                {
                    "One": dict(
                        messages=[],
                        result=dict(
                            level=STATUS_CODE["ERROR"],
                            id="ERROR_ID",
                            title="Error",
                            description="Action error",
                            diagnosis="User error",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                    "Two": dict(
                        messages=[],
                        result=dict(
                            level=STATUS_CODE["SKIP"],
                            id="SKIP_ID",
                            title="Skip",
                            description="Action skip",
                            diagnosis="User skip",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                    "Three": dict(
                        messages=[],
                        result=dict(
                            level=STATUS_CODE["SUCCESS"],
                            id="SUCCESS",
                            title="",
                            description="",
                            diagnosis="",
                            remediation="",
                            variables={},
                        ),
                    ),
                },
            ),
        ),
    )
    def test_run_actions(self, action_results, expected, monkeypatch):
        check_deps_mock = mock.Mock()
        run_mock = mock.Mock(return_value=action_results)

        monkeypatch.setattr(actions.Stage, "check_dependencies", check_deps_mock)
        monkeypatch.setattr(actions.Stage, "run", run_mock)

        assert actions.run_actions() == expected

    @pytest.mark.parametrize(
        ("action_results", "expected"),
        (
            # Only successes
            (
                actions.FinishedActions(
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[
                                ActionMessage(
                                    level="WARNING",
                                    id="WARNING_ID",
                                    title="Warning",
                                    description="Action warning",
                                    diagnosis="User warning",
                                    remediation="move on",
                                )
                            ],
                            result=ActionResult(level="SUCCESS", id="SUCCESS"),
                        ),
                    ],
                    [],
                    [],
                ),
                {
                    "One": dict(
                        messages=[
                            dict(
                                level=STATUS_CODE["WARNING"],
                                id="WARNING_ID",
                                title="Warning",
                                description="Action warning",
                                diagnosis="User warning",
                                remediation="move on",
                                variables={},
                            )
                        ],
                        result=dict(
                            level=STATUS_CODE["SUCCESS"],
                            id="SUCCESS",
                            title="",
                            description="",
                            diagnosis="",
                            remediation="",
                            variables={},
                        ),
                    )
                },
            ),
            (
                actions.FinishedActions(
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[
                                ActionMessage(
                                    level="WARNING",
                                    id="WARNING_ID",
                                    title="Warning",
                                    description="Action warning",
                                    diagnosis="User warning",
                                    remediation="move on",
                                )
                            ],
                            result=ActionResult(level="SUCCESS", id="SUCCESS"),
                            dependencies=("One",),
                        ),
                        _ActionForTesting(
                            id="Two",
                            messages=[
                                ActionMessage(
                                    level="WARNING",
                                    id="WARNING_ID",
                                    title="Warning",
                                    description="Action warning",
                                    diagnosis="User warning",
                                    remediation="move on",
                                )
                            ],
                            result=ActionResult(level="SUCCESS", id="SUCCESS"),
                            dependencies=(
                                "One",
                                "Two",
                            ),
                        ),
                    ],
                    [],
                    [],
                ),
                {
                    "One": dict(
                        messages=[
                            dict(
                                level=STATUS_CODE["WARNING"],
                                id="WARNING_ID",
                                title="Warning",
                                description="Action warning",
                                diagnosis="User warning",
                                remediation="move on",
                                variables={},
                            )
                        ],
                        result=dict(
                            level=STATUS_CODE["SUCCESS"],
                            id="SUCCESS",
                            title="",
                            description="",
                            diagnosis="",
                            remediation="",
                            variables={},
                        ),
                    ),
                    "Two": dict(
                        messages=[
                            dict(
                                level=STATUS_CODE["WARNING"],
                                id="WARNING_ID",
                                title="Warning",
                                description="Action warning",
                                diagnosis="User warning",
                                remediation="move on",
                                variables={},
                            )
                        ],
                        result=dict(
                            level=STATUS_CODE["SUCCESS"],
                            id="SUCCESS",
                            title="",
                            description="",
                            diagnosis="",
                            remediation="",
                            variables={},
                        ),
                    ),
                },
            ),
            # Single Failures
            (
                actions.FinishedActions(
                    [],
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[
                                ActionMessage(
                                    level="WARNING",
                                    id="WARNING_ID",
                                    title="Warning",
                                    description="Action warning",
                                    diagnosis="User warning",
                                    remediation="move on",
                                )
                            ],
                            result=ActionResult(
                                level="ERROR",
                                id="SOME_ERROR",
                                title="Error",
                                description="Action error",
                                diagnosis="User error",
                                remediation="move on",
                            ),
                        ),
                    ],
                    [],
                ),
                {
                    "One": dict(
                        messages=[
                            dict(
                                level=STATUS_CODE["WARNING"],
                                id="WARNING_ID",
                                title="Warning",
                                description="Action warning",
                                diagnosis="User warning",
                                remediation="move on",
                                variables={},
                            )
                        ],
                        result=dict(
                            level=STATUS_CODE["ERROR"],
                            id="SOME_ERROR",
                            title="Error",
                            description="Action error",
                            diagnosis="User error",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                },
            ),
            (
                actions.FinishedActions(
                    [],
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[
                                ActionMessage(
                                    level="WARNING",
                                    id="WARNING_ID",
                                    title="Warning",
                                    description="Action warning",
                                    diagnosis="User warning",
                                    remediation="move on",
                                )
                            ],
                            result=ActionResult(
                                level="OVERRIDABLE",
                                id="SOME_ERROR",
                                title="Overridable",
                                description="Action overridable",
                                diagnosis="User overridable",
                                remediation="move on",
                            ),
                        ),
                    ],
                    [],
                ),
                {
                    "One": dict(
                        messages=[
                            dict(
                                level=STATUS_CODE["WARNING"],
                                id="WARNING_ID",
                                title="Warning",
                                description="Action warning",
                                diagnosis="User warning",
                                remediation="move on",
                                variables={},
                            )
                        ],
                        result=dict(
                            level=STATUS_CODE["OVERRIDABLE"],
                            id="SOME_ERROR",
                            title="Overridable",
                            description="Action overridable",
                            diagnosis="User overridable",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                },
            ),
            (
                actions.FinishedActions(
                    [],
                    [],
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[
                                ActionMessage(
                                    level="WARNING",
                                    id="WARNING_ID",
                                    title="Warning",
                                    description="Action warning",
                                    diagnosis="User warning",
                                    remediation="move on",
                                )
                            ],
                            result=ActionResult(
                                level="SKIP",
                                id="SOME_ERROR",
                                title="Skip",
                                description="Action skip",
                                diagnosis="User skip",
                                remediation="move on",
                            ),
                        ),
                    ],
                ),
                {
                    "One": dict(
                        messages=[
                            dict(
                                level=STATUS_CODE["WARNING"],
                                id="WARNING_ID",
                                title="Warning",
                                description="Action warning",
                                diagnosis="User warning",
                                remediation="move on",
                                variables={},
                            )
                        ],
                        result=dict(
                            level=STATUS_CODE["SKIP"],
                            id="SOME_ERROR",
                            title="Skip",
                            description="Action skip",
                            diagnosis="User skip",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                },
            ),
            # Mixture of failures and successes.
            (
                actions.FinishedActions(
                    [
                        _ActionForTesting(
                            id="Three",
                            messages=[
                                ActionMessage(
                                    level="WARNING",
                                    id="WARNING_ID",
                                    title="Warning",
                                    description="Action warning",
                                    diagnosis="User warning",
                                    remediation="move on",
                                )
                            ],
                            result=ActionResult(level="SUCCESS", id="SUCCESS"),
                        ),
                    ],
                    [
                        _ActionForTesting(
                            id="One",
                            messages=[
                                ActionMessage(
                                    level="WARNING",
                                    id="WARNING_ID",
                                    title="Warning",
                                    description="Action warning",
                                    diagnosis="User warning",
                                    remediation="move on",
                                )
                            ],
                            result=ActionResult(
                                level="ERROR",
                                id="ERROR_ID",
                                title="Error",
                                description="Action error",
                                diagnosis="User error",
                                remediation="move on",
                            ),
                        ),
                    ],
                    [
                        _ActionForTesting(
                            id="Two",
                            messages=[
                                ActionMessage(
                                    level="WARNING",
                                    id="WARNING_ID",
                                    title="Warning",
                                    description="Action warning",
                                    diagnosis="User warning",
                                    remediation="move on",
                                )
                            ],
                            result=ActionResult(
                                level="SKIP",
                                id="SKIP_ID",
                                title="Skip",
                                description="Action skip",
                                diagnosis="User skip",
                                remediation="move on",
                            ),
                        ),
                    ],
                ),
                {
                    "One": dict(
                        messages=[
                            dict(
                                level=STATUS_CODE["WARNING"],
                                id="WARNING_ID",
                                title="Warning",
                                description="Action warning",
                                diagnosis="User warning",
                                remediation="move on",
                                variables={},
                            )
                        ],
                        result=dict(
                            level=STATUS_CODE["ERROR"],
                            id="ERROR_ID",
                            title="Error",
                            description="Action error",
                            diagnosis="User error",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                    "Two": dict(
                        messages=[
                            dict(
                                level=STATUS_CODE["WARNING"],
                                id="WARNING_ID",
                                title="Warning",
                                description="Action warning",
                                diagnosis="User warning",
                                remediation="move on",
                                variables={},
                            )
                        ],
                        result=dict(
                            level=STATUS_CODE["SKIP"],
                            id="SKIP_ID",
                            title="Skip",
                            description="Action skip",
                            diagnosis="User skip",
                            remediation="move on",
                            variables={},
                        ),
                    ),
                    "Three": dict(
                        messages=[
                            dict(
                                level=STATUS_CODE["WARNING"],
                                id="WARNING_ID",
                                title="Warning",
                                description="Action warning",
                                diagnosis="User warning",
                                remediation="move on",
                                variables={},
                            )
                        ],
                        result=dict(
                            level=STATUS_CODE["SUCCESS"],
                            id="SUCCESS",
                            title="",
                            description="",
                            diagnosis="",
                            remediation="",
                            variables={},
                        ),
                    ),
                },
            ),
        ),
    )
    def test_run_actions_with_messages(self, action_results, expected, monkeypatch):
        check_deps_mock = mock.Mock()
        run_mock = mock.Mock(return_value=action_results)

        monkeypatch.setattr(actions.Stage, "check_dependencies", check_deps_mock)
        monkeypatch.setattr(actions.Stage, "run", run_mock)

        results = actions.run_actions()
        assert results == expected

    def test_dependency_errors(self, monkeypatch, caplog):
        check_deps_mock = mock.Mock(side_effect=actions.DependencyError("Failure message"))
        monkeypatch.setattr(actions.Stage, "check_dependencies", check_deps_mock)

        with pytest.raises(SystemExit):
            actions.run_actions()

        assert (
            "Some dependencies were set on Actions but not present in convert2rhel: Failure message"
            == caplog.records[-1].message
        )


class TestFindFailedActions:
    test_results = {
        "BAD": dict(result=dict(level=STATUS_CODE["ERROR"], id="ERROR", message="Explosion")),
        "BAD2": dict(result=dict(level=STATUS_CODE["OVERRIDABLE"], id="OVERRIDABLE", message="Explosion")),
        "BAD3": dict(result=dict(level=STATUS_CODE["SKIP"], id="SKIP", message="Explosion")),
        "GOOD": dict(result=dict(level=STATUS_CODE["SUCCESS"], id="", message="No Error here")),
    }

    @pytest.mark.parametrize(
        ("severity", "expected_ids", "key"),
        (
            ("SUCCESS", ["BAD", "BAD2", "BAD3", "GOOD"], level_for_raw_action_data),
            ("SKIP", ["BAD", "BAD2", "BAD3"], level_for_raw_action_data),
            ("OVERRIDABLE", ["BAD", "BAD2"], level_for_raw_action_data),
            ("ERROR", ["BAD"], level_for_raw_action_data),
        ),
    )
    def test_find_actions_of_severity(self, severity, expected_ids, key):
        found_action_ids = sorted(a[0] for a in actions.find_actions_of_severity(self.test_results, severity, key))
        assert sorted(found_action_ids) == sorted(expected_ids)


class TestActionClasses:
    @pytest.mark.parametrize(
        ("id", "level", "title", "description", "diagnosis", "remediation", "expected"),
        (
            (
                "SUCCESS",
                "SUCCESS",
                None,
                None,
                None,
                None,
                dict(
                    id="SUCCESS",
                    level=STATUS_CODE["SUCCESS"],
                    title=None,
                    description=None,
                    diagnosis=None,
                    remediation=None,
                    variables={},
                ),
            ),
            (
                "SKIP_ID",
                "SKIP",
                "Skip message",
                "skip description",
                "skip diagnosis",
                "skip remediation",
                dict(
                    id="SKIP_ID",
                    level=STATUS_CODE["SKIP"],
                    title="Skip message",
                    description="skip description",
                    diagnosis="skip diagnosis",
                    remediation="skip remediation",
                    variables={},
                ),
            ),
            (
                "OVERRIDABLE_ID",
                "OVERRIDABLE",
                "Overridable message",
                "overridable description",
                "overridable diagnosis",
                "overridable remediation",
                dict(
                    id="OVERRIDABLE_ID",
                    level=STATUS_CODE["OVERRIDABLE"],
                    title="Overridable message",
                    description="overridable description",
                    diagnosis="overridable diagnosis",
                    remediation="overridable remediation",
                    variables={},
                ),
            ),
            (
                "ERROR_ID",
                "ERROR",
                "Error message",
                "error description",
                "error diagnosis",
                "error remediation",
                dict(
                    id="ERROR_ID",
                    level=STATUS_CODE["ERROR"],
                    title="Error message",
                    description="error description",
                    diagnosis="error diagnosis",
                    remediation="error remediation",
                    variables={},
                ),
            ),
        ),
    )
    def test_action_message_base(self, level, id, title, description, diagnosis, remediation, expected):
        action_message_base = ActionMessageBase(
            level=level, id=id, title=title, description=description, diagnosis=diagnosis, remediation=remediation
        )
        assert action_message_base.to_dict() == expected

    @pytest.mark.parametrize(
        ("id", "level", "title", "description", "diagnosis", "remediation", "expected"),
        (
            (None, None, None, None, None, None, "Messages require id, level, title and description fields"),
            ("SUCCESS_ID", None, None, None, None, None, "Messages require id, level, title and description fields"),
            (None, "SUCCESS", None, None, None, None, "Messages require id, level, title and description fields"),
            (
                None,
                None,
                "Success Message",
                None,
                None,
                None,
                "Messages require id, level, title and description fields",
            ),
            (
                None,
                None,
                None,
                "Success Description",
                None,
                None,
                "Messages require id, level, title and description fields",
            ),
            (
                "SUCCESS_ID",
                "SUCCESS",
                "Success message",
                "Description",
                None,
                None,
                "Invalid level 'SUCCESS', set for a non-result message",
            ),
            (
                "SKIP_ID",
                "SKIP",
                "Skip message",
                "Description",
                None,
                None,
                "Invalid level 'SKIP', set for a non-result message",
            ),
            (
                "OVERRIDABLE_ID",
                "OVERRIDABLE",
                "Overridable message",
                "Description",
                None,
                None,
                "Invalid level 'OVERRIDABLE', set for a non-result message",
            ),
            (
                "ERROR_ID",
                "ERROR",
                "Error message",
                "Description",
                None,
                None,
                "Invalid level 'ERROR', set for a non-result message",
            ),
        ),
    )
    def test_action_message_exceptions(self, level, id, title, description, diagnosis, remediation, expected):
        with pytest.raises(InvalidMessageError, match=expected):
            ActionMessage(
                level=level, id=id, title=title, description=description, diagnosis=diagnosis, remediation=remediation
            )

    @pytest.mark.parametrize(
        ("id", "level", "title", "description", "diagnosis", "remediation", "expected"),
        (
            (
                "WARNING_ID",
                "WARNING",
                "Warning message",
                "warning description",
                "warning diagnosis",
                "warning remediation",
                dict(
                    id="WARNING_ID",
                    level=STATUS_CODE["WARNING"],
                    title="Warning message",
                    description="warning description",
                    diagnosis="warning diagnosis",
                    remediation="warning remediation",
                    variables={},
                ),
            ),
            (
                "INFO_ID",
                "INFO",
                "Info message",
                "info description",
                "info diagnosis",
                "info remediation",
                dict(
                    id="INFO_ID",
                    level=STATUS_CODE["INFO"],
                    title="Info message",
                    description="info description",
                    diagnosis="info diagnosis",
                    remediation="info remediation",
                    variables={},
                ),
            ),
            (
                "INFO_ID",
                "INFO",
                "Info message",
                "info description",
                "info diagnosis",
                "info remediation",
                dict(
                    id="INFO_ID",
                    level=STATUS_CODE["INFO"],
                    title="Info message",
                    description="info description",
                    diagnosis="info diagnosis",
                    remediation="info remediation",
                ),
            ),
        ),
    )
    def test_action_message_success(self, level, id, title, description, diagnosis, remediation, expected):
        action_message = ActionMessage(
            level=level, id=id, title=title, description=description, diagnosis=diagnosis, remediation=remediation
        )
        assert action_message.to_dict() == expected

    @pytest.mark.parametrize(
        ("id", "level", "title", "description", "diagnosis", "remediation", "variables", "expected"),
        (
            (
                None,
                "ERROR",
                None,
                None,
                None,
                None,
                {},
                "Results require the id field",
            ),
            (
                "OVERRIDABLE_ID",
                "OVERRIDABLE",
                None,
                None,
                None,
                None,
                {},
                "Non-success results require level, title and description fields",
            ),
            (
                "ERROR_ID",
                "ERROR",
                "Title",
                None,
                None,
                None,
                {},
                "Non-success results require level, title and description fields",
            ),
            (
                "ERROR_ID",
                "ERROR",
                None,
                "Description",
                None,
                None,
                {},
                "Non-success results require level, title and description fields",
            ),
            (
                "WARNING_ID",
                "WARNING",
                "Warning message",
                "Warning description",
                "Warning diagnosis",
                "Warning remediation",
                {},
                "Invalid level 'WARNING', the level for result must be SKIP or more fatal or SUCCESS.",
            ),
        ),
    )
    def test_action_result_exceptions(self, level, id, title, description, diagnosis, remediation, variables, expected):
        with pytest.raises(InvalidMessageError, match=expected):
            ActionResult(
                level=level,
                id=id,
                title=title,
                description=description,
                diagnosis=diagnosis,
                remediation=remediation,
                variables=variables,
            )

    @pytest.mark.parametrize(
        ("id", "level", "title", "description", "diagnosis", "remediation", "variables", "expected"),
        (
            (
                "SUCCESS_ID",
                "SUCCESS",
                None,
                None,
                None,
                None,
                {},
                dict(
                    id="SUCCESS_ID",
                    level=STATUS_CODE["SUCCESS"],
                    title=None,
                    description=None,
                    diagnosis=None,
                    remediation=None,
                    variables={},
                ),
            ),
            (
                "SKIP_ID",
                "SKIP",
                "Skip",
                "skip description",
                "skip diagnosis",
                "skip remediation",
                {},
                dict(
                    id="SKIP_ID",
                    level=STATUS_CODE["SKIP"],
                    title="Skip",
                    description="skip description",
                    diagnosis="skip diagnosis",
                    remediation="skip remediation",
                    variables={},
                ),
            ),
            (
                "OVERRIDABLE_ID",
                "OVERRIDABLE",
                "Overridable",
                "overridable description",
                "overridable diagnosis",
                "overridable remediation",
                {},
                dict(
                    id="OVERRIDABLE_ID",
                    level=STATUS_CODE["OVERRIDABLE"],
                    title="Overridable",
                    description="overridable description",
                    diagnosis="overridable diagnosis",
                    remediation="overridable remediation",
                    variables={},
                ),
            ),
            (
                "ERROR_ID",
                "ERROR",
                "Error",
                "error description",
                "error diagnosis",
                "error remediation",
                {},
                dict(
                    id="ERROR_ID",
                    level=STATUS_CODE["ERROR"],
                    title="Error",
                    description="error description",
                    diagnosis="error diagnosis",
                    remediation="error remediation",
                    variables={},
                ),
            ),
        ),
    )
    def test_action_result_success(self, level, id, title, description, diagnosis, remediation, variables, expected):
        action_message = ActionResult(
            level=level,
            id=id,
            title=title,
            description=description,
            diagnosis=diagnosis,
            remediation=remediation,
            variables=variables,
        )
        assert action_message.to_dict() == expected


@pytest.mark.parametrize(
    ("status_code", "action_id", "id", "result", "expected"),
    (
        (
            STATUS_CODE["SUCCESS"],
            "Test",
            None,
            {},
            "(SUCCESS) Test: [No further information given]",
        ),
        (
            STATUS_CODE["WARNING"],
            "Test",
            "TestID",
            {
                "title": "A normal title",
                "description": "A normal description",
                "diagnosis": "A normal diagnosis",
                "remediation": "A normal remediation",
            },
            "(WARNING) Test.TestID: A normal title\n Description: A normal description\n Diagnosis: A normal diagnosis\n Remediation: A normal remediation\n",
        ),
        (
            STATUS_CODE["ERROR"],
            "Test",
            "TestID",
            {
                "title": "A normal title",
                "description": "",
                "diagnosis": "A normal diagnosis",
                "remediation": "A normal remediation",
            },
            "(ERROR) Test.TestID: A normal title\n Description: [No further information given]\n Diagnosis: A normal diagnosis\n Remediation: A normal remediation\n",
        ),
        (
            STATUS_CODE["ERROR"],
            "Test",
            "TestID",
            {
                "title": "A normal title",
                "description": "",
                "diagnosis": "",
                "remediation": "",
            },
            "(ERROR) Test.TestID: A normal title\n Description: [No further information given]\n Diagnosis: [No further information given]\n Remediation: [No further information given]\n",
        ),
    ),
)
def test_format_action_status_message(status_code, action_id, id, result, expected):
    message = actions.format_action_status_message(status_code, action_id, id, result)
    assert message in expected
