# -*- coding: utf-8 -*-
#
# Copyright(C) 2022 Red Hat, Inc.
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

import six


@six.add_metaclass(abc.ABCMeta)
class TransactionHandlerBase:
    """Abstract class that defines a common interface for the handlers.

    This class is not meant to have actual code implementation, only abstract
    methods that will have a "contract" between the other transaction handlers
    classes that inherit it in their implementation, thus, overriding the
    actual usage of the public methods listed here.

    _base: yum.YumBase | dnf.Base
        Instance of the base class, either YumBase() or Base()
    _enabled_repos: list[str]
        List of repositories to be enabled.
    """

    @abc.abstractmethod
    def __init__(self):
        self._base = None
        self._enabled_repos = []

    @abc.abstractmethod
    def run_transaction(self, test_transaction=False):
        """Run the actual transaction for the base class.

        :param test_transaction: Determines if the transaction needs to be tested or not.
        :type test_transaction: bool
        """
        pass
