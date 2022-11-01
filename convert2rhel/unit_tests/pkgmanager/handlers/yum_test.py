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

import os

import pytest
import six

from convert2rhel import pkgmanager, unit_tests, utils
from convert2rhel.pkgmanager.handlers.yum import YumTransactionHandler
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests.conftest import centos7


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class YumResolveDepsMocked(unit_tests.MockFunction):
    def __init__(self, start_at=0, loop_until=2):
        self.called = start_at
        self.loop_until = loop_until

    def __call__(self, *args, **kwargs):
        self.called += 1
        if self.called >= self.loop_until:
            return True
        else:
            return False


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
class TestYumTransactionHandler(object):
    @pytest.fixture
    def _mock_yum_api_calls(self, monkeypatch):
        """ """
        monkeypatch.setattr(pkgmanager.RepoStorage, "enableRepo", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.RepoStorage, "disableRepo", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "update", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "reinstall", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "downgrade", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "resolveDeps", value=mock.Mock(return_value=(0, "Success.")))
        monkeypatch.setattr(pkgmanager.YumBase, "processTransaction", value=mock.Mock())

    @centos7
    def test_set_up_base(self, pretend_os):
        instance = YumTransactionHandler()
        instance._set_up_base()

        assert isinstance(instance._base, pkgmanager.YumBase)
        assert instance._base.conf.yumvar["releasever"] == "7Server"

    @centos7
    @pytest.mark.parametrize(("enabled_rhel_repos"), ((["rhel-7-test-repo"])))
    def test_enable_repos(self, pretend_os, enabled_rhel_repos, _mock_yum_api_calls, caplog, monkeypatch):
        instance = YumTransactionHandler()
        instance._set_up_base()

        monkeypatch.setattr(system_info, "get_enabled_rhel_repos", lambda: enabled_rhel_repos)
        instance._enable_repos()

        assert "Enabling RHEL repositories:\n%s" % "\n".join(enabled_rhel_repos) in caplog.records[-1].message
        assert pkgmanager.RepoStorage.disableRepo.called_once()
        assert pkgmanager.RepoStorage.enableRepo.call_count == len(enabled_rhel_repos)

    @centos7
    @pytest.mark.parametrize(
        ("system_packages"),
        ((["pkg-1", "pkg-2", "pkg-3"],)),
    )
    def test_perform_operations(self, pretend_os, system_packages, _mock_yum_api_calls, caplog, monkeypatch):
        monkeypatch.setattr(pkgmanager.handlers.yum, "get_system_packages_for_replacement", lambda: system_packages)
        instance = YumTransactionHandler()
        instance._perform_operations()

        assert pkgmanager.YumBase.update.call_count == len(system_packages)
        assert pkgmanager.YumBase.reinstall.call_count == len(system_packages)
        assert pkgmanager.YumBase.downgrade.call_count == 0

    @centos7
    @pytest.mark.parametrize(
        ("system_packages"),
        ((["pkg-1", "pkg-2", "pkg-3"],)),
    )
    def test_perform_operations_reinstall_exception(
        self, pretend_os, system_packages, _mock_yum_api_calls, caplog, monkeypatch
    ):
        monkeypatch.setattr(pkgmanager.handlers.yum, "get_system_packages_for_replacement", lambda: system_packages)
        pkgmanager.YumBase.reinstall.side_effect = pkgmanager.Errors.ReinstallInstallError
        instance = YumTransactionHandler()
        instance._perform_operations()

        assert pkgmanager.YumBase.reinstall.call_count == len(system_packages)
        assert pkgmanager.YumBase.downgrade.call_count == len(system_packages)
        assert "not available in RHEL repositories" not in caplog.records[-1].message

    @centos7
    @pytest.mark.parametrize(
        ("system_packages"),
        ((["pkg-1", "pkg-2", "pkg-3"],)),
    )
    def test_perform_operations_downgrade_exception(
        self, pretend_os, system_packages, _mock_yum_api_calls, caplog, monkeypatch
    ):
        monkeypatch.setattr(pkgmanager.handlers.yum, "get_system_packages_for_replacement", lambda: system_packages)
        pkgmanager.YumBase.reinstall.side_effect = pkgmanager.Errors.ReinstallInstallError
        pkgmanager.YumBase.downgrade.side_effect = pkgmanager.Errors.ReinstallRemoveError
        instance = YumTransactionHandler()
        instance._perform_operations()

        assert pkgmanager.YumBase.reinstall.call_count == len(system_packages)
        assert pkgmanager.YumBase.downgrade.call_count == len(system_packages)
        assert "not available in RHEL repositories." in caplog.records[-1].message

    @centos7
    @pytest.mark.parametrize(
        ("ret_code", "message", "validate_transaction", "expected"),
        (
            (0, "success", True, True),
            (1, "failed", True, False),
            (1, "failed", False, False),
            (1, "Depsolving loop limit reached", True, False),
        ),
    )
    def test_resolve_dependencies(
        self, pretend_os, ret_code, message, validate_transaction, expected, _mock_yum_api_calls, caplog, monkeypatch
    ):
        monkeypatch.setattr(
            pkgmanager.YumBase,
            "resolveDeps",
            lambda _: (
                ret_code,
                message,
            ),
        )
        monkeypatch.setattr(pkgmanager.handlers.yum, "_resolve_yum_problematic_dependencies", mock.Mock())
        instance = YumTransactionHandler()
        instance._set_up_base()
        result = instance._resolve_dependencies(validate_transaction)

        if expected:
            assert pkgmanager.handlers.yum._resolve_yum_problematic_dependencies.call_count == 0
        assert result == expected

    @pytest.mark.parametrize(
        ("validate_transaction", "expected"),
        (
            (True, "Successfully validated the yum transaction set."),
            (False, "System packages replaced successfully."),
        ),
    )
    @centos7
    def test_process_transaction(self, pretend_os, validate_transaction, expected, _mock_yum_api_calls, caplog):
        instance = YumTransactionHandler()
        instance._set_up_base()

        instance._process_transaction(validate_transaction)
        assert expected in caplog.records[-1].message

    @centos7
    def test_process_transaction_with_exceptions(self, pretend_os, _mock_yum_api_calls, caplog):
        side_effects = (
            pkgmanager.Errors.YumRPMCheckError,
            pkgmanager.Errors.YumTestTransactionError,
            pkgmanager.Errors.YumRPMTransError,
        )
        instance = YumTransactionHandler()
        instance._set_up_base()
        pkgmanager.YumBase.processTransaction.side_effect = side_effects

        with pytest.raises(SystemExit):
            instance._process_transaction(validate_transaction=False)

        assert "Failed to validate the yum transaction." in caplog.records[-1].message

    @centos7
    @pytest.mark.parametrize(
        ("validate_transaction", "expected"),
        (
            (True, "Validating the yum transaction set, no modifications to the system will happen this time."),
            (False, "Replacing CentOS Linux packages."),
        ),
    )
    def test_run_transaction(
        self, pretend_os, validate_transaction, expected, _mock_yum_api_calls, caplog, monkeypatch
    ):
        monkeypatch.setattr(pkgmanager.handlers.yum.YumTransactionHandler, "_perform_operations", mock.Mock())
        monkeypatch.setattr(
            pkgmanager.handlers.yum.YumTransactionHandler, "_resolve_dependencies", YumResolveDepsMocked(loop_until=0)
        )
        monkeypatch.setattr(pkgmanager.handlers.yum.YumTransactionHandler, "_process_transaction", mock.Mock())
        instance = YumTransactionHandler()
        instance._set_up_base()
        instance.run_transaction(validate_transaction=validate_transaction)

        assert pkgmanager.handlers.yum.YumTransactionHandler._perform_operations.call_count == 1
        assert pkgmanager.handlers.yum.YumTransactionHandler._process_transaction.call_count == 1

    @centos7
    @pytest.mark.parametrize(("start_at", "loop_until"), ((0, 99), (4, 99)))
    def test_run_transaction_resolve_dependencies_loop(
        self, pretend_os, start_at, loop_until, _mock_yum_api_calls, caplog, monkeypatch
    ):
        monkeypatch.setattr(pkgmanager.handlers.yum.YumTransactionHandler, "_perform_operations", mock.Mock())
        monkeypatch.setattr(
            pkgmanager.handlers.yum.YumTransactionHandler,
            "_resolve_dependencies",
            YumResolveDepsMocked(start_at, loop_until),
        )
        instance = YumTransactionHandler()

        with pytest.raises(SystemExit):
            instance.run_transaction(validate_transaction=False)

        assert "Failed to resolve dependencies in the transaction." in caplog.records[-1].message


@centos7
@pytest.mark.parametrize(
    ("output", "expected_remove_pkgs"),
    (
        # A real case
        (
            [
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-core(x86-64) = 4.1-27.el7.centos.1",
                "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch requires python2-hawkey >= 0.7.0",
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-submod-security(x86-64) = 4.1-27.el7.centos.1",
                "ldb-tools-1.5.4-2.el7.x86_64 requires libldb(x86-64) = 1.5.4-2.el7",
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-submod-multimedia(x86-64) = 4.1-27.el7.centos.1",
                "python2-dnf-4.0.9.2-2.el7_9.noarch requires python2-hawkey >= 0.22.5",
                "abrt-retrace-client-2.1.11-60.el7.centos.x86_64 requires abrt = 2.1.11-60.el7.centos",
            ],
            frozenset(
                (
                    "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64",
                    "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch",
                    "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64",
                    "ldb-tools-1.5.4-2.el7.x86_64",
                    "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64",
                    "python2-dnf-4.0.9.2-2.el7_9.noarch",
                    "abrt-retrace-client-2.1.11-60.el7.centos.x86_64",
                )
            ),
        ),
        # Prevent duplicate entries
        (
            [
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-core(x86-64) = 4.1-27.el7.centos.1",
                "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 requires redhat-lsb-core(x86-64) = 4.1-27.el7.centos.1",
                "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch requires python2-hawkey >= 0.7.0",
                "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch requires python2-hawkey >= 0.7.0",
                "abrt-retrace-client-2.1.11-60.el7.centos.x86_64 requires abrt = 2.1.11-60.el7.centos",
            ],
            frozenset(
                (
                    "redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64",
                    "python2-dnf-plugins-core-4.0.2.2-3.el7_6.noarch",
                    "abrt-retrace-client-2.1.11-60.el7.centos.x86_64",
                )
            ),
        ),
        # Random string - This might not happen that frequently.
        (
            ["testing the test random string"],
            frozenset(()),
        ),
    ),
)
def test_resolve_yum_problematic_dependencies(
    pretend_os,
    output,
    expected_remove_pkgs,
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(pkgmanager.handlers.yum, "remove_pkgs", mock.Mock())
    pkgmanager.handlers.yum._resolve_yum_problematic_dependencies(output)

    if expected_remove_pkgs:
        assert pkgmanager.handlers.yum.remove_pkgs.called
        pkgmanager.handlers.yum.remove_pkgs.assert_called_with(
            pkgs_to_remove=expected_remove_pkgs,
            backup=True,
            critical=True,
            reposdir=utils.BACKUP_DIR,
            set_releasever=True,
            custom_releasever=7,
            varsdir=os.path.join(utils.BACKUP_DIR, "yum/vars"),
        )
    else:
        assert "Unable to resolve dependency issues." in caplog.records[-1].message
