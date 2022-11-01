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
from convert2rhel.pkgmanager.handlers.dnf import DnfTransactionHandler
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class RepoDict:
    def __init__(self, id):
        self.id = id
        self.disabled = False
        self.enabled = False

    def disable(self):
        self.disabled = True
        self.enabled = False

    def enable(self):
        self.enabled = True
        self.disabled = False


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
class TestDnfTransactionHandler:
    @pytest.fixture
    def _mock_dnf_api_calls(self, monkeypatch):
        """Mocks all calls related to the dnf API transactions"""
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

    @centos8
    def test_set_up_base(self, pretend_os):
        instance = DnfTransactionHandler()
        instance._set_up_base()

        assert isinstance(instance._base, pkgmanager.Base)
        assert instance._base.conf.substitutions["releasever"] == "8.4"
        assert instance._base.conf.module_platform_id == "platform:el8"

    @centos8
    @pytest.mark.parametrize(
        ("enabled_repos", "enabled_rhel_repos", "is_disabled", "is_enabled"),
        (
            (
                [RepoDict("rhel-8-repo-test")],
                ["rhel-8-repo-test", "test"],
                False,
                True,
            ),
            (
                [RepoDict("rhel-8-repo-test")],
                ["test"],
                True,
                False,
            ),
            (
                [RepoDict("rhel-8-repo-test")],
                ["rhel-8-repo-test", "test"],
                False,
                True,
            ),
        ),
    )
    def test_enable_repos(
        self,
        pretend_os,
        enabled_repos,
        enabled_rhel_repos,
        is_disabled,
        is_enabled,
        _mock_dnf_api_calls,
        caplog,
        monkeypatch,
    ):
        instance = DnfTransactionHandler()
        instance._set_up_base()
        pkgmanager.repodict.RepoDict.all = mock.Mock(return_value=enabled_repos)
        monkeypatch.setattr(system_info, "get_enabled_rhel_repos", lambda: enabled_rhel_repos)
        instance._enable_repos()

        assert "Enabling RHEL repositories:\n%s" % "\n".join(enabled_rhel_repos) in caplog.records[-1].message

        for repo in enabled_repos:
            assert repo.enabled == is_enabled
            assert repo.disabled == is_disabled

    @centos8
    @pytest.mark.parametrize(
        ("enabled_repos", "enabled_rhel_repos", "is_disabled", "is_enabled"),
        (
            (
                [RepoDict("rhel-8-repo-test")],
                ["rhel-8-repo-test", "test"],
                False,
                True,
            ),
        ),
    )
    def test_enable_repos_repo_error_exception(
        self,
        pretend_os,
        enabled_repos,
        enabled_rhel_repos,
        is_disabled,
        is_enabled,
        _mock_dnf_api_calls,
        caplog,
        monkeypatch,
    ):
        instance = DnfTransactionHandler()
        instance._set_up_base()
        pkgmanager.repodict.RepoDict.all = mock.Mock(return_value=enabled_repos)
        pkgmanager.Base.fill_sack = mock.Mock(side_effect=pkgmanager.exceptions.RepoError)
        with pytest.raises(SystemExit):
            instance._enable_repos()

        assert "Failed to populate repository metadata." in caplog.records[-1].message

    @centos8
    @pytest.mark.parametrize(
        ("system_packages"),
        ((["pkg-1", "pkg-2", "pkg-3"]),),
    )
    def test_perform_operations(self, pretend_os, system_packages, _mock_dnf_api_calls, caplog, monkeypatch):
        monkeypatch.setattr(
            pkgmanager.handlers.dnf,
            "get_system_packages_for_replacement",
            value=lambda: system_packages,
        )
        instance = DnfTransactionHandler()
        instance._set_up_base()
        instance._perform_operations()

        assert pkgmanager.Base.upgrade.call_count == len(system_packages)
        assert pkgmanager.Base.reinstall.call_count == len(system_packages)
        assert pkgmanager.Base.downgrade.call_count == 0

    @centos8
    @pytest.mark.parametrize(
        ("system_packages"),
        ((["pkg-1", "pkg-2", "pkg-3"]),),
    )
    def test_perform_operations_reinstall_exception(
        self, pretend_os, system_packages, _mock_dnf_api_calls, caplog, monkeypatch
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.dnf,
            "get_system_packages_for_replacement",
            value=lambda: system_packages,
        )
        pkgmanager.Base.reinstall.side_effect = pkgmanager.exceptions.PackagesNotAvailableError
        instance = DnfTransactionHandler()
        instance._set_up_base()
        instance._perform_operations()

        assert pkgmanager.Base.reinstall.call_count == len(system_packages)
        assert pkgmanager.Base.downgrade.call_count == len(system_packages)
        assert "not available in RHEL repositories" not in caplog.records[-1].message

    @centos8
    @pytest.mark.parametrize(
        ("system_packages"),
        ((["pkg-1", "pkg-2", "pkg-3"]),),
    )
    def test_perform_operations_downgrade_exception(
        self, pretend_os, system_packages, _mock_dnf_api_calls, caplog, monkeypatch
    ):
        monkeypatch.setattr(
            pkgmanager.handlers.dnf,
            "get_system_packages_for_replacement",
            value=lambda: system_packages,
        )
        pkgmanager.Base.reinstall.side_effect = pkgmanager.exceptions.PackagesNotAvailableError
        pkgmanager.Base.downgrade.side_effect = pkgmanager.exceptions.PackagesNotInstalledError

        instance = DnfTransactionHandler()
        instance._set_up_base()
        instance._perform_operations()

        assert pkgmanager.Base.reinstall.call_count == len(system_packages)
        assert pkgmanager.Base.downgrade.call_count == len(system_packages)
        assert "not available in RHEL repositories" in caplog.records[-1].message

    @centos8
    def test_resolve_dependencies(self, pretend_os, _mock_dnf_api_calls, caplog, monkeypatch):
        instance = DnfTransactionHandler()
        instance._set_up_base()
        instance._resolve_dependencies()

        assert pkgmanager.Base.resolve.call_count == 1
        assert pkgmanager.Base.download_packages.call_count == 1
        assert "Resolving the dependencies of the packages in the dnf transaction set." in caplog.records[-2].message

    @centos8
    def test_resolve_dependencies_resolve_exception(self, pretend_os, _mock_dnf_api_calls, caplog, monkeypatch):
        pkgmanager.Base.resolve.side_effect = pkgmanager.exceptions.DepsolveError
        instance = DnfTransactionHandler()
        instance._set_up_base()

        with pytest.raises(SystemExit):
            instance._resolve_dependencies()

        assert pkgmanager.Base.resolve.call_count == 1
        assert "Failed to resolve dependencies in the transaction." in caplog.records[-1].message

    @centos8
    def test_resolve_dependencies_download_pkgs_exception(self, pretend_os, _mock_dnf_api_calls, caplog, monkeypatch):
        pkgmanager.Base.download_packages.side_effect = pkgmanager.exceptions.DownloadError({"t": "test"})
        instance = DnfTransactionHandler()
        instance._set_up_base()

        with pytest.raises(SystemExit):
            instance._resolve_dependencies()

        assert pkgmanager.Base.resolve.call_count == 1
        assert pkgmanager.Base.download_packages.call_count == 1
        assert "Failed to download the transaction packages." in caplog.records[-1].message

    @pytest.mark.parametrize(
        ("validate_transaction", "expected"),
        (
            (True, "Successfully validated the dnf transaction set."),
            (False, "System packages replaced successfully."),
        ),
    )
    @centos8
    def test_process_transaction(self, pretend_os, validate_transaction, expected, _mock_dnf_api_calls, caplog):
        instance = DnfTransactionHandler()
        instance._set_up_base()
        instance._process_transaction(validate_transaction)

        assert pkgmanager.Base.do_transaction.called_once()
        assert expected in caplog.records[-1].message

    @centos8
    def test_process_transaction_exceptions(self, pretend_os, _mock_dnf_api_calls, caplog):
        side_effects = (
            pkgmanager.exceptions.Error,
            pkgmanager.exceptions.TransactionCheckError,
        )
        pkgmanager.Base.do_transaction.side_effect = side_effects
        instance = DnfTransactionHandler()
        instance._set_up_base()

        with pytest.raises(SystemExit):
            instance._process_transaction(validate_transaction=False)

        assert pkgmanager.Base.do_transaction.called_once()
        assert "Failed to validate the dnf transaction." in caplog.records[-1].message

    @centos8
    @pytest.mark.parametrize(
        ("validate_transaction"),
        ((True), (False)),
    )
    def test_run_transaction(self, pretend_os, validate_transaction, _mock_dnf_api_calls, caplog, monkeypatch):
        monkeypatch.setattr(pkgmanager.handlers.dnf.DnfTransactionHandler, "_enable_repos", mock.Mock())
        monkeypatch.setattr(pkgmanager.handlers.dnf.DnfTransactionHandler, "_perform_operations", mock.Mock())
        monkeypatch.setattr(pkgmanager.handlers.dnf.DnfTransactionHandler, "_resolve_dependencies", mock.Mock())
        monkeypatch.setattr(pkgmanager.handlers.dnf.DnfTransactionHandler, "_process_transaction", mock.Mock())
        instance = DnfTransactionHandler()

        instance.run_transaction(validate_transaction=validate_transaction)

        assert instance._enable_repos.call_count == 1
        assert instance._perform_operations.call_count == 1
        assert instance._resolve_dependencies.call_count == 1
        assert instance._process_transaction.call_count == 1
