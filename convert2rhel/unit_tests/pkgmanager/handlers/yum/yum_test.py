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
__metaclass__ = type

import hashlib
import os

import pytest
import six


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import backup, exceptions, pkghandler, pkgmanager
from convert2rhel.pkgmanager.handlers.yum import YumTransactionHandler
from convert2rhel.repo import DEFAULT_YUM_REPOFILE_DIR, DEFAULT_YUM_VARS_DIR
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests import RemovePkgsMocked, create_pkg_information, mock_decorator
from convert2rhel.unit_tests.conftest import centos7


SYSTEM_PACKAGES = [
    create_pkg_information(
        packager="test",
        vendor="test",
        name="pkg-1",
        epoch="0",
        version="1.0.0",
        release="1",
        arch="x86_64",
        fingerprint="24c6a8a7f4a80eb5",
        signature="test",
    ),
    create_pkg_information(
        packager="test",
        vendor="test",
        name="pkg-2",
        epoch="0",
        version="1.0.0",
        release="1",
        arch="x86_64",
        fingerprint="24c6a8a7f4a80eb5",
        signature="test",
    ),
    create_pkg_information(
        packager="test",
        vendor="test",
        name="pkg-3",
        epoch="0",
        version="1.0.0",
        release="1",
        arch="x86_64",
        fingerprint="24c6a8a7f4a80eb5",
        signature="test",
    ),
]


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
class TestYumTransactionHandler:
    @pytest.fixture(autouse=True)
    def _mock_yum_api_calls(self, monkeypatch):
        """ """
        monkeypatch.setattr(pkgmanager.RepoStorage, "enableRepo", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.RepoStorage, "disableRepo", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "update", value=mock.Mock(return_value=[]))
        monkeypatch.setattr(pkgmanager.YumBase, "reinstall", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "downgrade", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "resolveDeps", value=mock.Mock(return_value=(0, "Success.")))
        monkeypatch.setattr(pkgmanager.YumBase, "processTransaction", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "install", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "remove", value=mock.Mock())
        monkeypatch.setattr(pkgmanager.YumBase, "close", value=mock.Mock())

    @centos7
    def test_set_up_base(self, pretend_os):
        instance = YumTransactionHandler()
        instance._set_up_base()

        assert isinstance(instance._base, pkgmanager.YumBase)
        assert instance._base.conf.yumvar["releasever"] == "7Server"

    @centos7
    @pytest.mark.parametrize(
        ("enabled_rhel_repos",),
        (
            (
                [
                    "rhel-7-test-repo",
                ],
            ),
        ),
    )
    def test_enable_repos(self, pretend_os, enabled_rhel_repos, caplog, monkeypatch):
        instance = YumTransactionHandler()
        instance._set_up_base()

        monkeypatch.setattr(system_info, "get_enabled_rhel_repos", lambda: enabled_rhel_repos)
        instance._enable_repos()

        assert "Enabling RHEL repositories:\n%s" % "".join(enabled_rhel_repos) in caplog.records[-1].message
        assert pkgmanager.RepoStorage.disableRepo.called_once()
        assert pkgmanager.RepoStorage.enableRepo.call_count == len(enabled_rhel_repos)

    @centos7
    @pytest.mark.parametrize(
        ("enabled_rhel_repos",),
        (
            (
                [
                    "rhel-7-test-repo",
                ],
            ),
        ),
    )
    def test_enable_repos_repo_error(self, pretend_os, enabled_rhel_repos, caplog, monkeypatch):
        instance = YumTransactionHandler()
        instance._set_up_base()

        monkeypatch.setattr(system_info, "get_enabled_rhel_repos", lambda: enabled_rhel_repos)
        monkeypatch.setattr(pkgmanager.RepoStorage, "enableRepo", mock.Mock(side_effect=pkgmanager.Errors.RepoError))
        with pytest.raises(exceptions.CriticalError):
            instance._enable_repos()

        assert pkgmanager.RepoStorage.disableRepo.call_count == 1
        assert "Failed to populate repository metadata." in caplog.records[-1].message

    @centos7
    def test_perform_operations(self, pretend_os, monkeypatch):
        swap_base_os_specific_packages = mock.Mock()

        monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda: SYSTEM_PACKAGES)
        monkeypatch.setattr(YumTransactionHandler, "_swap_base_os_specific_packages", swap_base_os_specific_packages)
        instance = YumTransactionHandler()
        instance._set_up_base()
        instance._perform_operations()

        assert pkgmanager.YumBase.update.call_count == len(SYSTEM_PACKAGES)
        assert pkgmanager.YumBase.reinstall.call_count == len(SYSTEM_PACKAGES)
        assert pkgmanager.YumBase.downgrade.call_count == 0
        assert swap_base_os_specific_packages.call_count == 1

    @centos7
    def test_perform_operations_reinstall_exception(self, pretend_os, caplog, monkeypatch):
        monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda: SYSTEM_PACKAGES)
        pkgmanager.YumBase.reinstall.side_effect = pkgmanager.Errors.ReinstallInstallError
        instance = YumTransactionHandler()
        instance._set_up_base()
        instance._perform_operations()

        assert pkgmanager.YumBase.reinstall.call_count == len(SYSTEM_PACKAGES)
        assert pkgmanager.YumBase.downgrade.call_count == len(SYSTEM_PACKAGES)
        assert "not available in RHEL repositories" not in caplog.records[-1].message

    @centos7
    def test_perform_operations_downgrade_exception(self, pretend_os, caplog, monkeypatch):
        monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda: SYSTEM_PACKAGES)
        pkgmanager.YumBase.reinstall.side_effect = pkgmanager.Errors.ReinstallInstallError
        pkgmanager.YumBase.downgrade.side_effect = pkgmanager.Errors.ReinstallRemoveError
        instance = YumTransactionHandler()
        instance._set_up_base()
        instance._perform_operations()

        assert pkgmanager.YumBase.reinstall.call_count == len(SYSTEM_PACKAGES)
        assert pkgmanager.YumBase.downgrade.call_count == len(SYSTEM_PACKAGES)
        assert "not available in RHEL repositories." in caplog.text

    @centos7
    def test_perform_operations_no_more_mirrors_repo_exception(self, pretend_os, monkeypatch):
        monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda: SYSTEM_PACKAGES)
        pkgmanager.YumBase.update.side_effect = pkgmanager.Errors.NoMoreMirrorsRepoError
        instance = YumTransactionHandler()
        instance._set_up_base()
        with pytest.raises(exceptions.CriticalError):
            instance._perform_operations()

    @centos7
    @pytest.mark.parametrize(
        (
            "ret_code",
            "message",
            "expected",
        ),
        (
            (0, "success", None),
            (1, "failed", "failed"),
        ),
    )
    def test_resolve_dependencies(self, pretend_os, ret_code, message, expected, monkeypatch):
        monkeypatch.setattr(
            pkgmanager.YumBase,
            "resolveDeps",
            lambda _: (
                ret_code,
                message,
            ),
        )
        instance = YumTransactionHandler()
        instance._set_up_base()
        result = instance._resolve_dependencies()

        assert result == expected

    @pytest.mark.parametrize(
        ("validate_transaction", "expected"),
        (
            (True, "Successfully validated the yum transaction set."),
            (False, "System packages replaced successfully."),
        ),
    )
    @centos7
    def test_process_transaction(self, pretend_os, validate_transaction, expected, caplog):
        instance = YumTransactionHandler()
        instance._set_up_base()

        instance._process_transaction(validate_transaction)
        assert expected in caplog.records[-1].message

    @centos7
    def test_process_transaction_with_exceptions(self, pretend_os, caplog):
        side_effects = pkgmanager.Errors.YumBaseError
        instance = YumTransactionHandler()
        instance._set_up_base()
        pkgmanager.YumBase.processTransaction.side_effect = side_effects

        with pytest.raises(exceptions.CriticalError):
            instance._process_transaction(validate_transaction=False)

        assert "Failed to validate the yum transaction." in caplog.records[-1].message

    @centos7
    def test_package_marked_for_update(self, pretend_os, monkeypatch):
        """
        Test that if a package is marked for update, we won't call reinstall or
        downgrade after that.

        This comes from: https://issues.redhat.com/browse/RHELC-899
        """
        monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda: SYSTEM_PACKAGES)
        pkgmanager.YumBase.update.return_value = [
            "something"
        ]  # We don't care about the value, only that if has something.

        instance = YumTransactionHandler()
        instance._set_up_base()
        instance._perform_operations()

        assert pkgmanager.YumBase.update.call_count == len(SYSTEM_PACKAGES)
        assert pkgmanager.YumBase.reinstall.call_count == 0
        assert pkgmanager.YumBase.downgrade.call_count == 0

    @centos7
    @pytest.mark.parametrize(
        ("installed_pkgs", "swap_pkgs", "swaps"),
        (
            (["pkg0", "pkg1"], {"pkg0": "new_pkg0", "pkg1": "new_pkg1"}, 2),
            (["pkg1"], {"pkg0": "new_pkg0", "pkg1": "new_pkg1"}, 1),
            ([], {"pkg0": "new_pkg0", "pkg1": "new_pkg1"}, 0),
            (["pkg0", "pkg1", "pkg2"], {}, 0),
            ([], {}, 0),
        ),
    )
    def test_swap_base_os_specific_packages(
        self, monkeypatch, installed_pkgs, swap_pkgs, _mock_yum_api_calls, pretend_os, swaps
    ):
        def return_installed(pkg):
            """Dynamically change the return value."""
            return True if pkg in installed_pkgs else False

        is_rpm_installed = mock.Mock(side_effect=return_installed)

        monkeypatch.setattr(system_info, "is_rpm_installed", value=is_rpm_installed)
        monkeypatch.setattr(system_info, "swap_pkgs", value=swap_pkgs)

        instance = YumTransactionHandler()
        # Need to setup the base, in the production code it's done in upper level
        instance._set_up_base()

        instance._swap_base_os_specific_packages()

        assert pkgmanager.YumBase.remove.call_count == swaps
        assert pkgmanager.YumBase.install.call_count == swaps

    @centos7
    @pytest.mark.parametrize(
        (
            "messages",
            "expected",
        ),
        (
            ("Test message", "Test message"),
            (None, None),
        ),
    )
    def test_run_transaction_subprocess(self, pretend_os, monkeypatch, messages, expected):
        monkeypatch.setattr(YumTransactionHandler, "_perform_operations", mock.Mock())
        monkeypatch.setattr(YumTransactionHandler, "_resolve_dependencies", mock.Mock(return_value=messages))
        monkeypatch.setattr(YumTransactionHandler, "_process_transaction", mock.Mock())

        original_func = YumTransactionHandler._run_transaction_subprocess.__wrapped__
        monkeypatch.setattr(YumTransactionHandler, "_run_transaction_subprocess", mock_decorator(original_func))

        instance = YumTransactionHandler()
        result = instance._run_transaction_subprocess(validate_transaction=True)

        assert instance._perform_operations.call_count == 1
        assert instance._resolve_dependencies.call_count == 1

        if not messages:
            assert instance._process_transaction.call_count == 1

        assert result == expected

    @centos7
    def test_run_transaction(self, pretend_os, monkeypatch, caplog):
        monkeypatch.setattr(YumTransactionHandler, "_run_transaction_subprocess", mock.Mock(return_value=None))
        instance = YumTransactionHandler()
        instance.run_transaction(True)

        # No messages in the output, meaning that it worked.
        assert len(caplog.records) == 0

    @centos7
    def test_run_transaction_reached_loop_max_attempts(self, pretend_os, monkeypatch, caplog):
        monkeypatch.setattr(pkgmanager.handlers.yum, "MAX_NUM_OF_ATTEMPTS_TO_RESOLVE_DEPS", 1)
        monkeypatch.setattr(
            YumTransactionHandler,
            "_run_transaction_subprocess",
            mock.Mock(return_value="Depsolving loop limit reached"),
        )
        instance = YumTransactionHandler()
        with pytest.raises(exceptions.CriticalError):
            instance.run_transaction(True)

        assert "Retrying to resolve dependencies 1" in caplog.records[-2].message
        assert "Failed to resolve dependencies in the transaction." in caplog.records[-1].message

    @centos7
    def test_run_transaction_critical_error_exception(self, _mock_yum_api_calls, pretend_os, monkeypatch, caplog):
        monkeypatch.setattr(pkgmanager.handlers.yum, "MAX_NUM_OF_ATTEMPTS_TO_RESOLVE_DEPS", -1)
        instance = YumTransactionHandler()
        instance._set_up_base()
        with pytest.raises(exceptions.CriticalError):
            instance.run_transaction(True)

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
    monkeypatch.setattr(pkgmanager.handlers.yum.backup, "backup_control", mock.Mock())
    monkeypatch.setattr(pkgmanager.handlers.yum, "RestorablePackage", mock.Mock())
    monkeypatch.setattr(pkgmanager.handlers.yum, "remove_pkgs", RemovePkgsMocked())
    pkgmanager.handlers.yum._resolve_yum_problematic_dependencies(output)

    if expected_remove_pkgs:
        assert pkgmanager.handlers.yum.remove_pkgs.called
        backedup_reposdir = os.path.join(backup.BACKUP_DIR, hashlib.md5(DEFAULT_YUM_REPOFILE_DIR.encode()).hexdigest())
        backedup_yum_varsdir = os.path.join(backup.BACKUP_DIR, hashlib.md5(DEFAULT_YUM_VARS_DIR.encode()).hexdigest())
        assert pkgmanager.handlers.yum.RestorablePackage.called
        pkgmanager.handlers.yum.RestorablePackage.assert_called_with(
            pkgs=expected_remove_pkgs,
            reposdir=backedup_reposdir,
            set_releasever=True,
            custom_releasever=7,
            varsdir=backedup_yum_varsdir,
        )
        pkgmanager.handlers.yum.remove_pkgs.assert_called_with(pkgs_to_remove=expected_remove_pkgs, critical=True)
    else:
        assert "Unable to resolve dependency issues." in caplog.records[-1].message
