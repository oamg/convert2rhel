from collections import namedtuple

import pytest
import six

from convert2rhel import pkgmanager
from convert2rhel.pkgmanager.handlers.dnf import DnfTransactionHandler
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


RepoDict = namedtuple("RepoDict", ["id", "disable", "enable"])


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
class TestDnfTransactionHandler:
    @pytest.fixture
    def _mock_dnf_api_transaction_calls(self, monkeypatch):
        """Mocks all calls related to the dnf API transactions

        This fixture is not intended for general use. It suits better the
        function `_process_dnf_transaction()`
        """
        monkeypatch.setattr(pkgmanager.Base, "read_all_repos", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.repodict.RepoDict, "all", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.Base, "fill_sack", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.Base, "upgrade", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.Base, "reinstall", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.Base, "downgrade", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.Base, "resolve", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.Base, "download_packages", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.Base, "do_transaction", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.Base, "transaction", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.handlers.dnf, "remove_pkgs", value=mock.Mock())

    @centos8
    @pytest.mark.skipif(
        pkgmanager.TYPE != "dnf",
        reason="No dnf module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs", "test_transaction"),
        (
            (
                [RepoDict("rhel-8-repo-test", lambda: False, lambda _: True)],
                ["package-1", "package-2", "package-3"],
                False,
            ),
            (
                [
                    RepoDict(
                        "rhel-8-repo-test",
                        lambda: False,
                        lambda _: True,
                    ),
                    RepoDict(
                        "rhel-8-repo-test2",
                        lambda: False,
                        lambda _: True,
                    ),
                ],
                ["package-1", "package-2", "package-3"],
                True,
            ),
        ),
    )
    def test_process_dnf_transaction(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        test_transaction,
        _mock_dnf_api_transaction_calls,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.dnf,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        pkgmanager.repodict.RepoDict.all = mock.Mock(
            return_value=enabled_repos,
        )
        instance = DnfTransactionHandler()
        instance.process_transaction(test_transaction)

        assert pkgmanager.Base.read_all_repos.called
        assert pkgmanager.repodict.RepoDict.all.called
        assert pkgmanager.Base.fill_sack.called
        assert pkgmanager.Base.upgrade.call_count == len(original_os_pkgs)
        assert pkgmanager.Base.reinstall.call_count == len(original_os_pkgs)
        assert not pkgmanager.Base.downgrade.called
        assert pkgmanager.Base.resolve.called
        assert pkgmanager.Base.download_packages.called
        assert pkgmanager.Base.do_transaction.called

    @centos8
    @pytest.mark.skipif(
        pkgmanager.TYPE != "dnf",
        reason="No dnf module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs"),
        (
            (
                [RepoDict("rhel-8-repo-test", lambda: False, lambda _: True)],
                ["package-1", "package-2", "package-3"],
            ),
            (
                [RepoDict("rhel-8-repo-test", lambda: False, lambda _: True)],
                ["package-1", "package-2", "package-3"],
            ),
        ),
    )
    def test_process_dnf_transaction_downgrade_pkgs(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        _mock_dnf_api_transaction_calls,
        caplog,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.dnf,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        pkgmanager.repodict.RepoDict.all = mock.Mock(return_value=enabled_repos)
        pkgmanager.Base.reinstall = mock.Mock(
            side_effect=pkgmanager.exceptions.PackagesNotAvailableError,
        )
        pkgmanager.Base.downgrade = mock.Mock(
            side_effect=pkgmanager.exceptions.PackagesNotInstalledError,
        )
        instance = DnfTransactionHandler()
        instance.process_transaction()

        assert pkgmanager.Base.read_all_repos.called
        assert pkgmanager.repodict.RepoDict.all.called
        assert pkgmanager.Base.fill_sack.called
        assert pkgmanager.Base.upgrade.call_count == len(original_os_pkgs)
        assert pkgmanager.Base.reinstall.call_count == len(original_os_pkgs)
        assert pkgmanager.Base.downgrade.call_count == len(original_os_pkgs)
        assert pkgmanager.Base.resolve.called
        assert pkgmanager.Base.download_packages.called
        assert pkgmanager.Base.do_transaction.called
        assert pkgmanager.handlers.dnf.remove_pkgs.called

    @centos8
    @pytest.mark.skipif(
        pkgmanager.TYPE != "dnf",
        reason="No dnf module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs"),
        (
            (
                [RepoDict("rhel-8-repo-test", lambda: False, lambda _: True)],
                ["package-1"],
            ),
        ),
    )
    def test_process_dnf_transaction_resolve_exceptions(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        _mock_dnf_api_transaction_calls,
        caplog,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.dnf,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        pkgmanager.repodict.RepoDict.all = mock.Mock(return_value=enabled_repos)
        pkgmanager.Base.resolve = mock.Mock(side_effect=pkgmanager.exceptions.DepsolveError)
        instance = DnfTransactionHandler()

        with pytest.raises(SystemExit):
            instance.process_transaction()

        assert "Failed to resolve dependencines in the transaction." in caplog.records[-1].message

    @centos8
    @pytest.mark.skipif(
        pkgmanager.TYPE != "dnf",
        reason="No dnf module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs"),
        (
            (
                [RepoDict("rhel-8-repo-test", lambda: False, lambda _: True)],
                ["package-1"],
            ),
        ),
    )
    def test_process_dnf_transaction_download_pkgs_exceptions(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        _mock_dnf_api_transaction_calls,
        caplog,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.dnf,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        pkgmanager.repodict.RepoDict.all = mock.Mock(return_value=enabled_repos)
        pkgmanager.Base.download_packages = mock.Mock(
            side_effect=pkgmanager.exceptions.DownloadError({"t": "test"}),
        )
        instance = DnfTransactionHandler()

        with pytest.raises(SystemExit):
            instance.process_transaction()

        assert "Failed to download the transaction packages." in caplog.records[-1].message

    @centos8
    @pytest.mark.skipif(
        pkgmanager.TYPE != "dnf",
        reason="No dnf module detected on the system, skipping it.",
    )
    @pytest.mark.parametrize(
        ("enabled_repos", "original_os_pkgs"),
        (
            (
                [RepoDict("rhel-8-repo-test", lambda: False, lambda _: True)],
                ["package-1"],
            ),
            (
                [RepoDict("rhel-8-repo-test", lambda: False, lambda _: True)],
                ["package-1"],
            ),
        ),
    )
    def test_process_dnf_transaction_do_transaction_exceptions(
        self,
        pretend_os,
        enabled_repos,
        original_os_pkgs,
        _mock_dnf_api_transaction_calls,
        caplog,
        monkeypatch,
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.dnf,
            "get_system_packages_for_replacement",
            value=lambda: original_os_pkgs,
        )
        pkgmanager.repodict.RepoDict.all = mock.Mock(return_value=enabled_repos)
        pkgmanager.Base.do_transaction = mock.Mock(
            side_effect=[
                pkgmanager.exceptions.Error,
                pkgmanager.exceptions.TransactionCheckError,
            ]
        )
        instance = DnfTransactionHandler()
        with pytest.raises(SystemExit):
            instance.process_transaction()

        assert "Failed to validate the dnf transaction." in caplog.records[-1].message
