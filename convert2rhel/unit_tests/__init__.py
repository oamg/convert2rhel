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

from functools import wraps
import os
try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest


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
    return result[:_MAX_LENGTH] + ' [truncated]...'


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
            standard_msg = '%s not found in %s' % (safe_repr(member),
                                                  safe_repr(container))
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
            return '%s : %s' % (standard_msg, msg)
        except UnicodeDecodeError:
            return '%s : %s' % (safe_repr(standard_msg), safe_repr(msg))


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
