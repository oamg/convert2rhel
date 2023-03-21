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

import pytest
import six

from convert2rhel import cert, pkghandler, repo, subscription, toolopts, unit_tests
from convert2rhel.actions import STATUS_CODE
from convert2rhel.actions.handle_packages import RemoveExcludedPackages, RemoveRepositoryFilesPackages
from convert2rhel.actions.subscription import PreSubscription, SubscribeSystem


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def pre_subscription_instance():
    return PreSubscription()


class SystemCertMock:
    def __init__(self):
        pass

    def __call__(self, *args, **kwds):
        return self

    def install(self):
        pass


def test_pre_subscription_dependency_order(pre_subscription_instance):
    expected_dependencies = ("REMOVE_EXCLUDED_PACKAGES",)

    assert expected_dependencies == pre_subscription_instance.dependencies


def test_pre_subscription_no_rhsm_option_detected(pre_subscription_instance, monkeypatch, caplog):
    monkeypatch.setattr(toolopts.tool_opts, "no_rhsm", True)

    pre_subscription_instance.run()

    assert "Detected --no-rhsm option. Skipping" in caplog.records[-1].message
    assert pre_subscription_instance.status == STATUS_CODE["SUCCESS"]


def test_pre_subscription_run(pre_subscription_instance, monkeypatch):
    monkeypatch.setattr(pkghandler, "install_gpg_keys", mock.Mock())
    monkeypatch.setattr(subscription, "download_rhsm_pkgs", mock.Mock())
    monkeypatch.setattr(subscription, "replace_subscription_manager", mock.Mock())
    monkeypatch.setattr(subscription, "verify_rhsm_installed", mock.Mock())
    monkeypatch.setattr(cert, "SystemCert", SystemCertMock())

    pre_subscription_instance.run()

    assert pre_subscription_instance.status == STATUS_CODE["SUCCESS"]
    assert pkghandler.install_gpg_keys.call_count == 1
    assert subscription.download_rhsm_pkgs.call_count == 1
    assert subscription.replace_subscription_manager.call_count == 1
    assert subscription.verify_rhsm_installed.call_count == 1


@pytest.mark.parametrize(
    ("exception", "expected_status"),
    (
        (SystemExit("Exiting..."), ("ERROR", "UNKNOWN_ERROR", "Exiting...")),
        (subscription.UnregisterError, ("ERROR", "UNABLE_TO_REGISTER", "Failed to unregister the system:")),
    ),
)
def test_pre_subscription_exceptions(exception, expected_status, pre_subscription_instance, monkeypatch):
    # In the actual code, the exceptions can happen at different stages, but
    # since it is a unit test, it doesn't matter what function will raise the
    # exception we want.
    monkeypatch.setattr(pkghandler, "install_gpg_keys", mock.Mock(side_effect=exception))

    pre_subscription_instance.run()

    status, error_id, message = expected_status
    unit_tests.assert_actions_result(pre_subscription_instance, status=status, error_id=error_id, message=message)


@pytest.fixture
def subscribe_system_instance():
    return SubscribeSystem()


def test_subscribe_system_dependency_order(subscribe_system_instance):
    expected_dependencies = (
        "REMOVE_REPOSITORY_FILES_PACKAGES",
        "PRE_SUBSCRIPTION",
    )

    assert expected_dependencies == subscribe_system_instance.dependencies


def test_subscribe_system_no_rhsm_option_detected(subscribe_system_instance, monkeypatch, caplog):
    monkeypatch.setattr(toolopts.tool_opts, "no_rhsm", True)

    subscribe_system_instance.run()

    assert "Detected --no-rhsm option. Skipping" in caplog.records[-1].message
    assert subscribe_system_instance.status == STATUS_CODE["SUCCESS"]


def test_subscribe_system_run(subscribe_system_instance, monkeypatch):
    monkeypatch.setattr(subscription, "subscribe_system", mock.Mock())
    monkeypatch.setattr(repo, "get_rhel_repoids", mock.Mock())
    monkeypatch.setattr(subscription, "check_needed_repos_availability", mock.Mock())
    monkeypatch.setattr(subscription, "disable_repos", mock.Mock())
    monkeypatch.setattr(subscription, "enable_repos", mock.Mock())

    subscribe_system_instance.run()

    assert subscribe_system_instance.status == STATUS_CODE["SUCCESS"]
    assert subscription.subscribe_system.call_count == 1
    assert repo.get_rhel_repoids.call_count == 1
    assert subscription.check_needed_repos_availability.call_count == 1
    assert subscription.disable_repos.call_count == 1
    assert subscription.enable_repos.call_count == 1


@pytest.mark.parametrize(
    ("exception", "expected_status"),
    (
        (IOError("/usr/bin/t"), ("ERROR", "MISSING_SUBSCRIPTION_MANAGER_BINARY", "Failed to execute command:")),
        (SystemExit("Exiting..."), ("ERROR", "UNKNOWN_ERROR", "Exiting...")),
        (
            ValueError,
            (
                "ERROR",
                "MISSING_REGISTRATION_COMBINATION",
                "One or more combinations were missing for subscription-manager parameters:",
            ),
        ),
    ),
)
def test_subscribe_system_exceptions(exception, expected_status, subscribe_system_instance, monkeypatch):
    # In the actual code, the exceptions can happen at different stages, but
    # since it is a unit test, it doesn't matter what function will raise the
    # exception we want.
    monkeypatch.setattr(subscription, "subscribe_system", mock.Mock(side_effect=exception))

    subscribe_system_instance.run()

    status, error_id, message = expected_status
    unit_tests.assert_actions_result(subscribe_system_instance, status=status, error_id=error_id, message=message)
