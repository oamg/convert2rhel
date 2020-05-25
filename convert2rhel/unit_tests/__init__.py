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

from convert2rhel import logger

TMP_DIR = "/tmp/convert2rhel_test/"
NONEXISTING_DIR = os.path.join(TMP_DIR, "nonexisting_dir/")
NONEXISTING_FILE = os.path.join(TMP_DIR, "nonexisting.file")
# Dummy file for built-in open function
DUMMY_FILE = os.path.join(os.path.dirname(__file__), "dummy_file")

try:
    from functools import wraps
except ImportError:
    """ functools.wrap is not available on Python 2.4

    On Centos/OL/RHEL 5 the available version of Python is 2.4 which does not have
    functools.wrap decorator used on our tests. Following the solution described
    here[0], following code is a copy from functools code from Python official
    repo[1]. Only the use of partial func was changed as described.

    [0] https://stackoverflow.com/questions/12274814/functools-wraps-for-python-2-4
    [1] https://hg.python.org/cpython/file/b48e1b48e670/Lib/functools.py
    """

    WRAPPER_ASSIGNMENTS = ('__module__', '__name__', '__doc__')
    WRAPPER_UPDATES = ('__dict__',)
    def update_wrapper(wrapper,
                       wrapped,
                       assigned = WRAPPER_ASSIGNMENTS,
                       updated = WRAPPER_UPDATES):
        """Update a wrapper function to look like the wrapped function

           wrapper is the function to be updated
           wrapped is the original function
           assigned is a tuple naming the attributes assigned directly
           from the wrapped function to the wrapper function (defaults to
           functools.WRAPPER_ASSIGNMENTS)
           updated is a tuple naming the attributes off the wrapper that
           are updated with the corresponding attribute from the wrapped
           function (defaults to functools.WRAPPER_UPDATES)
        """
        for attr in assigned:
            setattr(wrapper, attr, getattr(wrapped, attr))
        for attr in updated:
            getattr(wrapper, attr).update(getattr(wrapped, attr, {}))
        # Return the wrapper so this can be used as a decorator via partial()
        return wrapper


    def partial(func, *args, **kwds):
        "Emulate Python2.6's functools.partial"
        return lambda *fargs, **fkwds: func(*(args+fargs), **dict(kwds, **fkwds))


    def wraps(wrapped,
              assigned = WRAPPER_ASSIGNMENTS,
              updated = WRAPPER_UPDATES):
        """Decorator factory to apply update_wrapper() to a wrapper function

           Returns a decorator that invokes update_wrapper() with the decorated
           function as the wrapper argument and the arguments to wraps() as the
           remaining arguments. Default arguments are as for update_wrapper().
           This is a convenience function to simplify applying partial() to
           update_wrapper().
        """
        return partial(update_wrapper, wrapped=wrapped,
                       assigned=assigned, updated=updated)


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
    @tests.mock(utils, "run_subprocess", run_subprocess_mocked())
    -- replaces the original run_subprocess function from the utils module
       with the run_subprocess_mocked function.
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


class MockFunction(object):
    """
    This class should be used as a base class when creating a mocked
    function.

    Example:
    from convert2rhel import tests  # Imports tests/__init__.py
    class run_subprocess_mocked(tests.MockFunction):
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
