# -*- coding: utf-8 -*-
#
# Copyright(C) 2016 Red Hat, Inc.
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

import logging
import re

from convert2rhel import subscription, utils
from convert2rhel.backup import RestorableChange


loggerinst = logging.getLogger(__name__)


class RestorableSystemSubscription(RestorableChange):
    """
    Register with RHSM in a fashion that can be reverted.
    """

    # We need this __init__ because it is an abstractmethod in the base class
    def __init__(self):  # pylint: disable=useless-parent-delegation
        super(RestorableSystemSubscription, self).__init__()

    def enable(self):
        """Register and attach a specific subscription to OS."""
        if self.enabled:
            return

        subscription.register_system()
        subscription.attach_subscription()

        super(RestorableSystemSubscription, self).enable()

    def restore(self):
        """Rollback subscription related changes"""
        loggerinst.task("Rollback: RHSM-related actions")

        if self.enabled:
            try:
                subscription.unregister_system()
            except subscription.UnregisterError as e:
                loggerinst.warning(str(e))
            except OSError:
                loggerinst.warning("subscription-manager not installed, skipping")

        super(RestorableSystemSubscription, self).restore()


class RestorableAutoAttachmentSubscription(RestorableChange):
    """
    Auto attach subscriptions with RHSM in a fashion that can be reverted.
    """

    def __init__(self):
        super(RestorableAutoAttachmentSubscription, self).__init__()
        self._is_attached = False

    def enable(self):
        self._is_attached = subscription.auto_attach_subscription()
        super(RestorableAutoAttachmentSubscription, self).enable()

    def restore(self):
        if self._is_attached:
            subscription.remove_subscription()
            super(RestorableAutoAttachmentSubscription, self).restore()


class RestorableDisableRepositories(RestorableChange):
    """
    Gather repositories enabled on the system before we disable them and enable
    them in the rollback.
    """

    # Look for the `Repo ID` key in the subscription-manager output, if there
    # is a match, we save it in the named group `repo_id`. This will find all
    # occurrences of the Repo ID in the output.
    ENABLED_REPOS_PATTERN = re.compile(r"Repo ID:\s+(?P<repo_id>\S+)")

    def __init__(self):
        super(RestorableDisableRepositories, self).__init__()
        self._repos_to_enable = []

    def _get_enabled_repositories(self):
        """Get repositories that were enabled prior to the conversion.

        :returns list[str]: List of repositories enabled prior the conversion.
            If no repositories were enabled or match the ignored rhel
            repositories, defaults to an empty list.
        """
        cmd = ["subscription-manager", "repos", "--list-enabled"]
        output, _ = utils.run_subprocess(cmd, print_output=False)

        repositories = []
        matches = re.finditer(self.ENABLED_REPOS_PATTERN, output)
        if matches:
            repositories = [match.group("repo_id") for match in matches if match.group("repo_id")]

        return repositories

    def enable(self):
        repositories = self._get_enabled_repositories()

        if repositories:
            self._repos_to_enable = repositories
            loggerinst.debug("Repositories enabled in the system prior to the conversion: %s" % ",".join(repositories))

        subscription.disable_repos()
        super(RestorableDisableRepositories, self).enable()

    def restore(self):
        if not self.enabled:
            return

        loggerinst.task("Rollback: Restoring state of the repositories")

        if self._repos_to_enable:
            loggerinst.debug("Repositories to enable: %s" % ",".join(self._repos_to_enable))

            # This is not the ideal state. We should really have a generic
            # class for enabling/disabling the repositories we have touched for
            # RHSM. Jira issue: https://issues.redhat.com/browse/RHELC-1560
            subscription.disable_repos()
            subscription.submgr_enable_repos(self._repos_to_enable)

        super(RestorableDisableRepositories, self).restore()
