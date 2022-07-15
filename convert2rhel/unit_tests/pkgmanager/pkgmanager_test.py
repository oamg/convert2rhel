import pytest
import six

from convert2rhel import pkgmanager
from convert2rhel.unit_tests.conftest import all_systems


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
