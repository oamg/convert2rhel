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

"""
This is an example test file containing a simple test.
"""

import six

from convert2rhel import unit_tests, utils


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class RunSubprocessMocked(unit_tests.MockFunctionObject):
    """
    Simplest example of a mocked function.

    * Inherit from convert2rhel.unit_tests.MockFunctionObject
    * The convention is to end the class name with `*Mocked`
    * All of the methods of mock.Mock are available on this class.
    * Set the spec attribute to the function that you are mocking.
    """

    spec = utils.run_subprocess

    def __init__(self, ret=("Test", 0), **kwargs):
        """
        * Use __init__ to set any attributes that you want to keep track of or need to use in
          `__call__`.
        * The superclass will keep track of details about how the function is called.
        * It is good practice to accept kwargs here and pass them on to the superclass so that the
          user can customize the mocked function.  All the parameters taken by mock.Mock() are
          accepted by the superclass.
        * You may decide to construct your own parameters to pass to the superclass's `__init__`.
          These will ultimately be passed on to mock.Mock's `__init__`.  See
          `convert2rhel.unit_tests.CallYumCmdMocked` for an example of this.
        """
        self.prefix = "this ain't "
        self.ret = ret

        super(RunSubprocessMocked, self).__init__(**kwargs)

    def __call__(self, *args, **kwargs):
        """
        Implementation of the simplest behavior of a mocked function -
        ignore the input parameters and just return fake value.

        * The superclass will record all of the statistics about how this function was called
          so you don't need to implement your own except as conveniences for things you commonly
          check for this specific function.
        * Call the superclass's `__call__` method with all of the args and kwargs (including ones
          that you are also using here.  That is how the superclass keeps its records.
        * You can manipulate the return value here (as in this example) or by passing `return_value`
          or `side_effect` in `__init__` and returning the results of the superclass's `__call__`
          method here.
        """
        super(RunSubprocessMocked, self).__call__(*args, **kwargs)

        self.ret = (self.prefix + self.ret[0], self.ret[1])
        return self.ret


def test_example(monkeypatch):
    # Set a tuple to be returned by the RunSubprocessMocked function
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(ret=["ls output", 0]))

    output, ret_code = utils.run_subprocess("ls -l")

    assert output == "this ain't ls output"
    assert ret_code == 0
    assert utils.run_subprocess.prefix == "this ain't "
    assert utils.run_subprocess.call_count == 1
    assert utils.run_subprocess.call_args == mock.call("ls -l")
