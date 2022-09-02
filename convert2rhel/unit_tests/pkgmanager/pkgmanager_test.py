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

import pytest
import six

from convert2rhel import pkgmanager


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
def test_create_transaction_handler_yum(monkeypatch):
    yum_transaction_handler_mock = mock.Mock()
    monkeypatch.setattr(pkgmanager.handlers.yum, "YumTransactionHandler", yum_transaction_handler_mock)
    pkgmanager.create_transaction_handler()

    assert yum_transaction_handler_mock.called


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
def test_create_transaction_handler_dnf(monkeypatch):
    dnf_transaction_handler_mock = mock.Mock()
    monkeypatch.setattr(pkgmanager.handlers.dnf, "DnfTransactionHandler", dnf_transaction_handler_mock)
    pkgmanager.create_transaction_handler()

    assert dnf_transaction_handler_mock.called
