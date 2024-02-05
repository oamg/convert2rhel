# Copyright(C) 2023 Red Hat, Inc.
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

import os.path
import shutil

from functools import partial

import pytest
import six

from convert2rhel import actions, pkghandler, repo, subscription, toolopts, unit_tests
from convert2rhel.actions import STATUS_CODE
from convert2rhel.actions.pre_ponr_changes import subscription as appc_subscription
from convert2rhel.actions.pre_ponr_changes.subscription import PreSubscription, SubscribeSystem


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def pre_subscription_instance():
    return PreSubscription()


@pytest.fixture
def subscribe_system_instance():
    return SubscribeSystem()


@pytest.fixture
def install_repo_cert_instance():
    return appc_subscription.InstallRedHatCertForYumRepositories()


@pytest.fixture
def install_gpg_key_instance():
    return appc_subscription.InstallRedHatGpgKeyForRpm()


class TestInstallRedHatCertForYumRepositories:
    def test_run(self, monkeypatch, install_repo_cert_instance, restorable):
        monkeypatch.setattr(appc_subscription, "RestorablePEMCert", lambda x, y: restorable)
        install_repo_cert_instance.run()

        assert restorable.called["enable"] == 1


class TestInstallRedHatGpgKeyForRpm:
    def test_run(self, monkeypatch, install_gpg_key_instance):
        fake_install_gpg_keys = mock.Mock()
        monkeypatch.setattr(pkghandler, "install_gpg_keys", fake_install_gpg_keys)
        install_gpg_key_instance.run()

        assert fake_install_gpg_keys.call_count == 1


class TestPreSubscription:
    def test_pre_subscription_dependency_order(self, pre_subscription_instance):
        expected_dependencies = (
            "INSTALL_RED_HAT_CERT_FOR_YUM",
            "INSTALL_RED_HAT_GPG_KEY",
            "REMOVE_EXCLUDED_PACKAGES",
        )

        assert expected_dependencies == pre_subscription_instance.dependencies

    def test_pre_subscription_no_rhsm_option_detected(self, pre_subscription_instance, monkeypatch, caplog):
        monkeypatch.setattr(toolopts.tool_opts, "no_rhsm", True)
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="PRE_SUBSCRIPTION_CHECK_SKIP",
                    title="Pre-subscription check skip",
                    description="Detected --no-rhsm option. Did not perform the check.",
                    diagnosis=None,
                    remediations=None,
                ),
            )
        )

        pre_subscription_instance.run()

        assert "Detected --no-rhsm option. Did not perform the check." in caplog.records[-1].message
        assert pre_subscription_instance.result.level == STATUS_CODE["SUCCESS"]
        assert expected.issuperset(pre_subscription_instance.messages)
        assert expected.issubset(pre_subscription_instance.messages)

    @pytest.mark.parametrize(
        ("needed_subscription_manager_pkgs", "backup_will_partition"),
        (
            (["subscription-manager", "python3-syspurpose"], True),
            ([], False),
        ),
    )
    def test_pre_subscription_run(
        self,
        needed_subscription_manager_pkgs,
        backup_will_partition,
        pre_subscription_instance,
        monkeypatch,
        tmpdir,
        global_backup_control,
    ):
        monkeypatch.setattr(
            subscription, "needed_subscription_manager_pkgs", mock.Mock(return_value=needed_subscription_manager_pkgs)
        )
        monkeypatch.setattr(subscription, "install_rhel_subscription_manager", mock.Mock())
        monkeypatch.setattr(subscription, "verify_rhsm_installed", mock.Mock())

        red_hat_ca_dir = str(tmpdir)
        product_cert_dir = os.path.join(str(tmpdir), "rhel-certs")
        uninstalled_data_dir = os.path.join(os.path.dirname(__file__), "../../../data")
        os.makedirs(product_cert_dir)

        shutil.copy2(os.path.join(uninstalled_data_dir, "version-independent/redhat-uep.pem"), red_hat_ca_dir)
        shutil.copy2(os.path.join(uninstalled_data_dir, "8/x86_64/rhel-certs/479.pem"), product_cert_dir)

        monkeypatch.setattr(appc_subscription, "_REDHAT_CDN_CACERT_SOURCE_DIR", red_hat_ca_dir)
        monkeypatch.setattr(appc_subscription, "_RHSM_PRODUCT_CERT_SOURCE_DIR", product_cert_dir)
        monkeypatch.setattr(global_backup_control, "push", mock.Mock())

        pre_subscription_instance.run()

        assert pre_subscription_instance.result.level == STATUS_CODE["SUCCESS"]
        assert subscription.needed_subscription_manager_pkgs.call_count == 1
        assert subscription.install_rhel_subscription_manager.call_count == (
            1 if needed_subscription_manager_pkgs else 0
        )
        assert subscription.verify_rhsm_installed.call_count == 1
        assert global_backup_control.push.call_count == 2 if backup_will_partition else 1

    @pytest.mark.parametrize(
        ("exception", "expected_level"),
        (
            (
                SystemExit("Exiting..."),
                ("ERROR", "UNKNOWN_ERROR", "Unknown error", "The cause of this error is unknown", "Exiting..."),
            ),
        ),
    )
    def test_pre_subscription_exceptions(self, exception, expected_level, pre_subscription_instance, monkeypatch):
        # In the actual code, the exceptions can happen at different stages, but
        # since it is a unit test, it doesn't matter what function will raise the
        # exception we want.  This is the first function in the try except
        # block that we can test with.
        monkeypatch.setattr(subscription, "needed_subscription_manager_pkgs", mock.Mock(side_effect=exception))

        pre_subscription_instance.run()

        level, id, title, description, diagnosis = expected_level
        unit_tests.assert_actions_result(pre_subscription_instance, level=level, id=id, description=description)

    @pytest.mark.parametrize(
        ("exception", "expected_level"),
        (
            (
                subscription.UnregisterError,
                (
                    "ERROR",
                    "UNABLE_TO_REGISTER",
                    "System unregistration failure",
                    "The system is already registered with subscription-manager",
                    "Failed to unregister the system:",
                    "You may want to unregister the system manually",
                ),
            ),
        ),
    )
    def test_pre_subscription_exceptions_with_remediations(
        self, exception, expected_level, pre_subscription_instance, monkeypatch
    ):
        # In the actual code, the exceptions can happen at different stages, but
        # since it is a unit test, it doesn't matter what function will raise the
        # exception we want.  This is the first function in the try except
        # block that we can test with.
        monkeypatch.setattr(subscription, "needed_subscription_manager_pkgs", mock.Mock(side_effect=exception))

        pre_subscription_instance.run()

        level, id, title, description, diagnosis, remediations = expected_level
        unit_tests.assert_actions_result(
            pre_subscription_instance,
            level=level,
            id=id,
            description=description,
            diagnosis=diagnosis,
        )


class TestSubscribeSystem:
    def test_subscribe_system_dependency_order(self, subscribe_system_instance):
        expected_dependencies = ("REMOVE_REPOSITORY_FILES_PACKAGES", "PRE_SUBSCRIPTION", "EUS_SYSTEM_CHECK")

        assert expected_dependencies == subscribe_system_instance.dependencies

    def test_subscribe_system_do_not_subscribe(self, global_tool_opts, subscribe_system_instance, monkeypatch, caplog):
        global_tool_opts.no_rhsm = False
        # partial saves the real copy of tool_opts to use with
        # _should_subscribe so we have to monkeypatch with the mocked version
        # of tool_opts.
        monkeypatch.setattr(subscription, "should_subscribe", partial(toolopts._should_subscribe, global_tool_opts))
        monkeypatch.setattr(subscription.RestorableSystemSubscription, "enable", mock.Mock())
        monkeypatch.setattr(repo, "get_rhel_repoids", mock.Mock())
        monkeypatch.setattr(subscription, "disable_repos", mock.Mock())
        monkeypatch.setattr(subscription, "enable_repos", mock.Mock())

        fake_refresh = mock.Mock()
        monkeypatch.setattr(subscription, "refresh_subscription_info", fake_refresh)

        subscribe_system_instance.run()

        assert fake_refresh.call_count == 1

    def test_subscribe_system_no_rhsm_option_detected(
        self, global_tool_opts, subscribe_system_instance, monkeypatch, caplog
    ):
        global_tool_opts.no_rhsm = True
        # partial saves the real copy of tool_opts to use with
        # _should_subscribe so we have to monkeypatch with the mocked version
        # of tool_opts.
        monkeypatch.setattr(subscription, "should_subscribe", partial(toolopts._should_subscribe, global_tool_opts))

        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="SUBSCRIPTION_CHECK_SKIP",
                    title="Subscription check skip",
                    description="Detected --no-rhsm option. Did not perform the check.",
                    diagnosis=None,
                    remediations=None,
                ),
            )
        )

        subscribe_system_instance.run()

        assert "Detected --no-rhsm option. Did not perform subscription step." in caplog.records[-1].message
        assert subscribe_system_instance.result.level == STATUS_CODE["SUCCESS"]
        assert expected.issuperset(subscribe_system_instance.messages)
        assert expected.issubset(subscribe_system_instance.messages)

    def test_subscribe_system_run(self, subscribe_system_instance, monkeypatch):
        monkeypatch.setattr(subscription, "should_subscribe", lambda: True)
        monkeypatch.setattr(subscription.RestorableSystemSubscription, "enable", mock.Mock())
        monkeypatch.setattr(repo, "get_rhel_repoids", mock.Mock())
        monkeypatch.setattr(subscription, "disable_repos", mock.Mock())
        monkeypatch.setattr(subscription, "enable_repos", mock.Mock())

        subscribe_system_instance.run()

        assert subscribe_system_instance.result.level == STATUS_CODE["SUCCESS"]
        assert subscription.RestorableSystemSubscription.enable.call_count == 1
        assert repo.get_rhel_repoids.call_count == 1
        assert subscription.disable_repos.call_count == 1
        assert subscription.enable_repos.call_count == 1

    @pytest.mark.parametrize(
        ("exception", "expected_level"),
        (
            (
                SystemExit("Exiting..."),
                ("ERROR", "UNKNOWN_ERROR", "Unknown error", "The cause of this error is unknown", "Exiting..."),
            ),
            (
                ValueError,
                (
                    "ERROR",
                    "MISSING_REGISTRATION_COMBINATION",
                    "Missing registration combination",
                    "There are missing registration combinations",
                    "One or more combinations were missing for subscription-manager parameters:",
                ),
            ),
            (
                OSError("/usr/bin/t"),
                (
                    "ERROR",
                    "MISSING_SUBSCRIPTION_MANAGER_BINARY",
                    "Missing subscription-manager binary",
                    "There is a missing subscription-manager binary",
                    "Failed to execute command:",
                ),
            ),
        ),
    )
    def test_subscribe_system_exceptions(self, exception, expected_level, subscribe_system_instance, monkeypatch):
        monkeypatch.setattr(subscription, "should_subscribe", lambda: True)
        # In the actual code, the exceptions can happen at different stages, but
        # since it is a unit test, it doesn't matter what function will raise the
        # exception we want.
        monkeypatch.setattr(subscription.RestorableSystemSubscription, "enable", mock.Mock(side_effect=exception))

        subscribe_system_instance.run()

        level, id, title, description, diagnosis = expected_level
        unit_tests.assert_actions_result(
            subscribe_system_instance, level=level, id=id, title=title, description=description, diagnosis=diagnosis
        )
