# -*- coding: utf-8 -*-
#
# Copyright(C) 2024 Red Hat, Inc.
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

import errno

import pytest
import six

from convert2rhel.backup.subscription import (
    RestorableAutoAttachmentSubscription,
    RestorableDisableRepositories,
    RestorableSystemSubscription,
)


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import exceptions, subscription, utils
from convert2rhel.unit_tests import (
    AutoAttachSubscriptionMocked,
    RegisterSystemMocked,
    RemoveAutoAttachSubscriptionMocked,
    RunSubprocessMocked,
    UnregisterSystemMocked,
)


class TestRestorableSystemSubscription:
    @pytest.fixture
    def system_subscription(self):
        return RestorableSystemSubscription()

    def test_subscribe_system(self, system_subscription, global_tool_opts, monkeypatch):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        global_tool_opts.username = "user"
        global_tool_opts.password = "pass"

        system_subscription.enable()

        assert subscription.register_system.call_count == 1

    def test_subscribe_system_already_enabled(self, monkeypatch, system_subscription):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        system_subscription.enabled = True

        system_subscription.enable()

        assert not subscription.register_system.called

    def test_enable_fail_once(self, system_subscription, global_tool_opts, caplog, monkeypatch):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_code=1))
        global_tool_opts.username = "user"
        global_tool_opts.password = "pass"

        with pytest.raises(exceptions.CriticalError):
            system_subscription.enable()

        assert caplog.records[-1].levelname == "CRITICAL"

    def test_restore(self, monkeypatch, system_subscription):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(subscription, "attach_subscription", mock.Mock(return_value=True))

        monkeypatch.setattr(subscription, "unregister_system", UnregisterSystemMocked())
        system_subscription.enable()

        system_subscription.restore()
        assert subscription.unregister_system.call_count == 1

    def test_restore_not_enabled(self, monkeypatch, caplog, system_subscription):
        monkeypatch.setattr(subscription, "unregister_system", UnregisterSystemMocked())

        system_subscription.restore()

        assert not subscription.unregister_system.called

    def test_restore_unregister_call_fails(self, monkeypatch, caplog, system_subscription):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(subscription, "attach_subscription", mock.Mock(return_value=True))

        mocked_unregister_system = UnregisterSystemMocked(side_effect=subscription.UnregisterError("Unregister failed"))
        monkeypatch.setattr(subscription, "unregister_system", mocked_unregister_system)

        system_subscription.enable()

        system_subscription.restore()

        assert mocked_unregister_system.call_count == 1
        assert "Unregister failed" == caplog.records[-1].message

    def test_restore_subman_uninstalled(self, caplog, monkeypatch, system_subscription):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(subscription, "attach_subscription", mock.Mock(return_value=True))
        monkeypatch.setattr(
            subscription,
            "unregister_system",
            UnregisterSystemMocked(side_effect=OSError(errno.ENOENT, "command not found")),
        )
        system_subscription.enable()

        system_subscription.restore()

        assert "subscription-manager not installed, skipping" == caplog.messages[-1]


class TestRestorableAutoAttachmentSubscription:
    @pytest.fixture
    def auto_attach_subscription(self):
        return RestorableAutoAttachmentSubscription()

    def test_enable_auto_attach(self, auto_attach_subscription, monkeypatch):
        monkeypatch.setattr(subscription, "auto_attach_subscription", AutoAttachSubscriptionMocked())
        auto_attach_subscription.enable()
        assert subscription.auto_attach_subscription.call_count == 1

    def test_restore_auto_attach(self, auto_attach_subscription, monkeypatch):
        monkeypatch.setattr(subscription, "remove_subscription", RemoveAutoAttachSubscriptionMocked())
        monkeypatch.setattr(subscription, "auto_attach_subscription", mock.Mock(return_value=True))
        auto_attach_subscription.enable()
        auto_attach_subscription.restore()
        assert subscription.remove_subscription.call_count == 1

    def test_restore_auto_attach_not_enabled(self, auto_attach_subscription, monkeypatch):
        monkeypatch.setattr(subscription, "remove_subscription", RemoveAutoAttachSubscriptionMocked())
        auto_attach_subscription.restore()
        assert subscription.remove_subscription.call_count == 0

    def test_already_enabled(self, auto_attach_subscription, monkeypatch):
        monkeypatch.setattr(subscription, "auto_attach_subscription", mock.Mock())
        auto_attach_subscription.enabled = True

        auto_attach_subscription.enable()

        assert subscription.auto_attach_subscription.call_count == 0


class TestRestorableDisableRepositories:
    @pytest.mark.parametrize(
        (
            "output",
            "expected",
        ),
        (
            (
                """
+----------------------------------------------------------+
    Available Repositories in /etc/yum.repos.d/redhat.repo
+----------------------------------------------------------+
Repo ID:   Test_Repository_ID
Repo Name: Updates x86_64
Repo URL:  https://test_repository.id
Enabled:   1

Repo ID:   Satellite_Engineering_CentOS_7_Base_x86_64
Repo Name: Base x86_64
Repo URL:  https://Satellite_Engineering_CentOS_7_Base.x86_64
Enabled:   1
""",
                ["Test_Repository_ID", "Satellite_Engineering_CentOS_7_Base_x86_64"],
            ),
            (
                """
+----------------------------------------------------------+
    Available Repositories in /etc/yum.repos.d/redhat.repo
+----------------------------------------------------------+
Repo ID:   RHEL_Repository
Repo Name: Updates x86_64
Repo URL:  https://test_repository.id
Enabled:   1

Repo ID:   Satellite_Engineering_CentOS_7_Base_x86_64
Repo Name: Base x86_64
Repo URL:  https://Satellite_Engineering_CentOS_7_Base.x86_64
Enabled:   1
""",
                ["RHEL_Repository", "Satellite_Engineering_CentOS_7_Base_x86_64"],
            ),
            (
                """
+----------------------------------------------------------+
    Available Repositories in /etc/yum.repos.d/redhat.repo
+----------------------------------------------------------+
Repo ID:   RHEL_Repository
Repo Name: Updates x86_64
Repo URL:  https://test_repository.id
Enabled:   1
""",
                ["RHEL_Repository"],
            ),
            ("There were no available repositories matching the specified criteria.", []),
        ),
    )
    def test_get_enabled_repositories(self, output, expected, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=(output, 0)))
        results = RestorableDisableRepositories()._get_enabled_repositories()
        assert results == expected
        assert utils.run_subprocess.call_count == 1

    @pytest.mark.parametrize(
        (
            "enabled_repositories",
            "log_message",
        ),
        (
            (
                ["Test_Repo"],
                "Repositories enabled in the system prior to the conversion: %s",
            ),
            (
                [],
                None,
            ),
        ),
    )
    def test_enable(self, enabled_repositories, log_message, monkeypatch, caplog):
        monkeypatch.setattr(
            RestorableDisableRepositories, "_get_enabled_repositories", mock.Mock(return_value=enabled_repositories)
        )
        monkeypatch.setattr(subscription, "disable_repos", mock.Mock())

        action = RestorableDisableRepositories()
        action.enable()

        assert action.enabled
        assert subscription.disable_repos.call_count == 1

        if log_message:
            assert action._repos_to_enable == enabled_repositories
            assert log_message % ",".join(enabled_repositories) in caplog.records[-1].message

    @pytest.mark.parametrize(
        (
            "enabled_repositories",
            "log_message",
        ),
        (
            (
                ["Test_Repo"],
                "Repositories to enable: %s",
            ),
            (
                [],
                None,
            ),
        ),
    )
    def test_restore(self, enabled_repositories, log_message, monkeypatch, caplog):
        monkeypatch.setattr(subscription, "submgr_enable_repos", mock.Mock())
        monkeypatch.setattr(subscription, "disable_repos", mock.Mock())
        action = RestorableDisableRepositories()
        action.enabled = True
        action._repos_to_enable = enabled_repositories

        action.restore()

        assert not action.enabled
        if log_message:
            assert action._repos_to_enable == enabled_repositories
            assert subscription.submgr_enable_repos.call_count == 1
            assert log_message % ",".join(enabled_repositories) in caplog.records[-1].message

    def test_not_enabled_restore(self):
        action = RestorableDisableRepositories()
        action.restore()

        assert not action.enabled
