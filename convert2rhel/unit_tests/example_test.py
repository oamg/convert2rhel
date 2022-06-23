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

from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel import utils


class RunSubprocessMocked(unit_tests.MockFunction):
    def __call__(self, *args, **kwargs):
        """
        Implementation of the simplest behavior of a mocked function -
        ignore the input parameters and just return fake value.
        """
        self.prefix = "this ain't "
        self.ret = (self.prefix + self.ret[0], self.ret[1])
        return self.ret


def test_example(monkeypatch):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
    # Set a tuple to be returned by the RunSubprocessMocked function
    utils.run_subprocess.ret = ("ls output", 0)

    output, ret_code = utils.run_subprocess("ls -l")

    assert output == "this ain't ls output"
    assert ret_code == 0
    assert utils.run_subprocess.prefix == "this ain't "
