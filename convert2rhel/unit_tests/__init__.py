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

import os
import unittest

from functools import wraps

import pytest

from convert2rhel.utils import run_subprocess


TMP_DIR = "/tmp/convert2rhel_test/"
NONEXISTING_DIR = os.path.join(TMP_DIR, "nonexisting_dir/")
NONEXISTING_FILE = os.path.join(TMP_DIR, "nonexisting.file")
# Dummy file for built-in open function
DUMMY_FILE = os.path.join(os.path.dirname(__file__), "dummy_file")
_MAX_LENGTH = 80


def mock(class_or_module, orig_obj, mock_obj):
    """
    This is a decorator to be applied to any test method that needs to mock
    some module/class object (be it function, method or variable). It replaces
    the original object with any arbitrary object. The original is still
    accessible through "<original object name>_orig" attribute.

    Parameters:
    class_or_module - module/class in which the original function/method is
                      defined
    orig_obj - name of the original object as a string
    mock_obj - object that will replace the orig_obj, for example:
               -- instance of some fake function
               -- string

    Example:
    @tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    -- replaces the original run_subprocess function from the utils module
       with the RunSubprocessMocked function.
    @tests.mock(logging.FileHandler, "_open", FileHandler_open_mocked())
    -- replaces the original _open method of the FileHandler class within
       the logging module with the FileHandler_open_mocked function.
    @tests.mock(gpgkey, "gpg_key_system_dir", "/nonexisting_dir/")
    -- replaces the gpgkey module-scoped variable gpg_key_system_dir with the
       "/nonexisting_dir/" string
    """

    def wrap(func):
        # The @wraps decorator below makes sure the original object name
        # and docstring (in case of a method/function) are preserved.
        @wraps(func)
        def wrapped_fn(*args, **kwargs):
            # Save temporarily the original object
            orig_obj_saved = getattr(class_or_module, orig_obj)
            # Replace the original object with the mocked one
            setattr(class_or_module, orig_obj, mock_obj)
            # To be able to use the original object within the mocked object
            # (e.g. to have the mocked function just as a wrapper for the
            # original function), save it as a temporary attribute
            # named "<original object name>_orig"
            orig_obj_attr = "%s_orig" % orig_obj
            setattr(class_or_module, orig_obj_attr, orig_obj_saved)
            # Call the decorated test function
            return_value = None
            try:
                try:
                    return_value = func(*args, **kwargs)
                except:
                    raise
            finally:
                # NOTE: finally need to be used in this way for Python 2.4
                # Restore the original object
                setattr(class_or_module, orig_obj, orig_obj_saved)
                # Remove the temporary attribute holding the original object
                delattr(class_or_module, orig_obj_attr)
            return return_value

        return wrapped_fn

    return wrap


def safe_repr(obj, short=False):
    """
    Safetly calls repr().
    Returns a truncated string if repr message is too long.
    """
    try:
        result = repr(obj)
    except Exception:
        result = object.__repr__(obj)
    if not short or len(result) < _MAX_LENGTH:
        return result
    return result[:_MAX_LENGTH] + " [truncated]..."


def get_pytest_marker(request, mark_name):
    """
    Get a pytest mark from a request.

    The pytest API to retrieve a mark changed between RHEL7. This function is
    a compatibility shim to retrieve the value.

    Use this function instead of pytest's `request.node.get_closest_marker(mark_name)` so that it will work on all versions of RHEL that we are targeting.
    .. seealso::
        * `pytest's get_closest_marker() function which this function wraps <https://docs.pytest.org/en/stable/reference/reference.html#pytest.nodes.Node.get_closest_marker>`_
        * `A technique you might use where you would need to use this function to retrieve a mark's value. <https://docs.pytest.org/en/stable/how-to/fixtures.html#using-markers-to-pass-data-to-fixtures>`_
    """
    if pytest.__version__.split(".") <= ["3", "6", "0"]:
        mark = request.node.get_marker(mark_name)
    else:
        mark = request.node.get_closest_marker(mark_name)

    return mark


class ExtendedTestCase(unittest.TestCase):
    """
    Extends Nose test case with more helpers.
    Most of these functions are taken from newer versions of Nose
    test and can be removed when we upgrade Nose test.
    """

    def assertIn(self, member, container, msg=None):
        """
        Taken from newer nose test version.
        Just like self.assertTrue(a in b), but with a nicer default message.
        """
        if member not in container:
            standard_msg = "%s not found in %s" % (
                safe_repr(member),
                safe_repr(container),
            )
            self.fail(self._formatMessage(msg, standard_msg))

    def _formatMessage(self, msg, standard_msg):
        """
        Taken from newer nose test version.
        Formats the message in a safe manner for better readability.
        """
        if msg is None:
            return standard_msg
        try:
            # don't switch to '{}' formatting in Python 2.X
            # it changes the way unicode input is handled
            return "%s : %s" % (standard_msg, msg)
        except UnicodeDecodeError:
            return "%s : %s" % (safe_repr(standard_msg), safe_repr(msg))


class MockFunction(object):
    """
    This class should be used as a base class when creating a mocked
    function.

    Example:
    from convert2rhel import tests  # Imports tests/__init__.py
    class RunSubprocessMocked(tests.MockFunction):
        ...
    """

    def __call__(self):
        """
        To be implemented when inheriting this class. The input parameters
        should either mimic the parameters of the original function/method OR
        use generic input parameters (*args, **kwargs).

        Examples:
        def __call__(self, cmd, print_output=True, shell=False):
            # ret_val to be set within the test or within __init__ first
            return self.ret_val

        def __call__(self, *args, **kwargs):
            pass
        """


class CountableMockObject(MockFunction):
    def __init__(self, *args, **kwargs):
        self.called = 0

    def __call__(self, *args, **kwargs):
        self.called += 1
        return


def is_rpm_based_os():
    """Check if the OS is rpm based."""
    try:
        run_subprocess(["rpm"])
    except EnvironmentError:
        return False
    else:
        return True


class GetLoggerMocked(MockFunction):
    def __init__(self):
        self.task_msgs = []
        self.info_msgs = []
        self.warning_msgs = []
        self.critical_msgs = []
        self.error_msgs = []
        self.debug_msgs = []

    def __call__(self, msg):
        return self

    def critical(self, msg, *args):
        self.critical_msgs.append(msg)
        raise SystemExit(1)

    def error(self, msg, *args):
        self.error_msgs.append(msg)

    def task(self, msg, *args):
        self.task_msgs.append(msg)

    def info(self, msg, *args):
        self.info_msgs.append(msg)

    def warn(self, msg, *args):
        self.warning_msgs.append(msg)

    def warning(self, msg, *args):
        self.warn(msg, *args)

    def debug(self, msg, *args):
        self.debug_msgs.append(msg)


class GetFileContentMocked(MockFunction):
    def __init__(self, data, as_list=True):
        self.data = data
        self.as_list = as_list
        self.called = 0

    def __call__(self, filename, as_list):
        self.called += 1
        self.as_list = as_list
        return [x.strip() for x in self.data] if self.as_list else self.data


def run_subprocess_side_effect(*stubs):
    """Side effect function for utils.run_subprocess.
    :type stubs: Tuple[Tuple[command, ...], Tuple[command_stdout, exit_code]]

    Allows you to parametrize the mocking by providing list of stubs

    if run_subprocess called with args, which are not specified in
    stubs, then no mocking happening and a real subprocess call will be made.

    Example:
    >>> run_subprocess_mock = mock.Mock(
    >>>     side_effect=run_subprocess_side_effect(
    >>>         (("uname",), ("5.8.0-7642-generic\n", 0)),
    >>>         (("repoquery", "-f"), (REPOQUERY_F_STUB_GOOD, 0)),
    >>>         (("repoquery", "-l"), (REPOQUERY_L_STUB_GOOD, 0)),
    >>>     )
    >>> )
    """

    def factory(*args, **kwargs):
        for kws, result in stubs:
            if all(kw in args[0] for kw in kws):
                return result
        else:
            return run_subprocess(*args, **kwargs)

    return factory
