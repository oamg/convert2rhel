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

from convert2rhel import repo
from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel.systeminfo import system_info


class TestRepo(unit_tests.ExtendedTestCase):
    @unit_tests.mock(system_info, "default_rhsm_repoids", ["rhel_server"])
    def test_get_rhel_repoids(self):
        repos = repo.get_rhel_repoids()

        self.assertEqual(repos, ["rhel_server"])
