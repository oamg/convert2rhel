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

import logging

from convert2rhel import actions, cert, pkghandler, repo, subscription, toolopts


logger = logging.getLogger(__name__)


class PreSubscription(actions.Action):
    id = "PRE_SUBSCRIPTION"
    dependencies = ("REMOVE_EXCLUDED_PACKAGES",)

    def run(self):
        super(PreSubscription, self).run()

        if toolopts.tool_opts.no_rhsm:
            logger.warning("Detected --no-rhsm option. Skipping.")
            self.add_message(
                level="WARNING",
                id="PRE_SUBSCRIPTION_CHECK_SKIP",
                title="Pre-subscription check skip",
                description="Detected --no-rhsm option. Skipping.",
            )
            return

        try:
            # TODO(r0x0d): Check later if we can move this piece to be an independant
            # check, rather than one step in the pre-subscription, as this is
            # not only used for subscription-manager, but for installing the
            # packages later with yum transaction.

            # Import the Red Hat GPG Keys for installing Subscription-manager
            # and for later.
            logger.task("Convert: Import Red Hat GPG keys")
            pkghandler.install_gpg_keys()

            logger.task("Convert: Subscription Manager - Download packages")
            subscription.download_rhsm_pkgs()

            logger.task("Convert: Subscription Manager - Replace")
            subscription.replace_subscription_manager()

            logger.task("Convert: Subscription Manager - Verify installation")
            subscription.verify_rhsm_installed()

            logger.task("Convert: Install RHEL certificates for RHSM")
            cert.SystemCert().install()
        except SystemExit as e:
            # TODO(r0x0d): Places where we raise SystemExit and need to be
            # changed to something more specific.
            #   - If we can't import the gpg key.
            #   - if directory does not exist or is empty
            #   - if we can't download a package
            #   - if we can't install sub-man rpms
            #   - If sub-man is not installed and --keep-rhsm was used.

            # TODO(r0x0d): This should be refactored to handle each case
            # individually rather than relying on SystemExit.
            self.set_result(
                level="ERROR",
                id="UNKNOWN_ERROR",
                title="Unknown error",
                description="The cause of this error is unknown, please look at the diagnosis for more information.",
                diagnosis=str(e),
            )
        except subscription.UnregisterError as e:
            self.set_result(
                level="ERROR",
                id="UNABLE_TO_REGISTER",
                title="System unregistration failure",
                description="The system is already registered with subscription-manager even though it is running CentOS not RHEL. We have failed to remove that registration.",
                diagnosis="Failed to unregister the system: %s" % e,
                remediation="You may want to unregister the system manually and re-run convert2rhel.",
            )


class SubscribeSystem(actions.Action):
    id = "SUBSCRIBE_SYSTEM"
    dependencies = (
        # Implicit dependency for `BACKUP_REDHAT_RELEASE`
        "REMOVE_REPOSITORY_FILES_PACKAGES",
        "PRE_SUBSCRIPTION",
    )

    def run(self):
        super(SubscribeSystem, self).run()

        if toolopts.tool_opts.no_rhsm:
            logger.warning("Detected --no-rhsm option. Skipping.")
            self.add_message(
                level="WARNING",
                id="SUBSCRIPTION_CHECK_SKIP",
                title="Subscription check skip",
                description="Detected --no-rhsm option. Skipping.",
            )
            return

        try:
            logger.task("Convert: Subscription Manager - Subscribe system")
            subscription.subscribe_system()

            logger.task("Convert: Get RHEL repository IDs")
            rhel_repoids = repo.get_rhel_repoids()

            logger.task("Convert: Subscription Manager - Disable all repositories")
            subscription.disable_repos()

            # we need to enable repos after removing repofile pkgs, otherwise
            # we don't get backups to restore from on a rollback
            logger.task("Convert: Subscription Manager - Enable RHEL repositories")
            subscription.enable_repos(rhel_repoids)
        except IOError as e:
            # TODO(r0x0d): Places where we raise IOError and need to be
            # changed to something more specific.
            #  - Could fail in invoking subscription-manager to get repos     (get_avail_repos)
            #  - Could fail in invoking subscirption-manager to disable repos (disable_repos)
            #  - ""                                          to enable repos  (enable_repos)
            self.set_result(
                level="ERROR",
                id="MISSING_SUBSCRIPTION_MANAGER_BINARY",
                title="Missing subscription-manager binary",
                description="There is a missing subscription-manager binary",
                diagnosis="Failed to execute command: %s" % e,
            )
        except SystemExit as e:
            # TODO(r0x0d): This should be refactored to handle each case
            # individually rather than relying on SystemExit.

            # TODO(r0x0d): Places where we raise SystemExit and need to be
            # changed to something more specific.
            #   - Maximum sub-man retries reached
            #   - If the return-code is different from 0 in disabling repos,
            #     SystemExit is raised.
            self.set_result(
                level="ERROR",
                id="UNKNOWN_ERROR",
                title="Unknown error",
                description="The cause of this error is unknown, please look at the diagnosis for more information.",
                diagnosis=str(e),
            )
        except ValueError as e:
            self.set_result(
                level="ERROR",
                id="MISSING_REGISTRATION_COMBINATION",
                title="Missing registration combination",
                description="There are missing registration combinations",
                diagnosis="One or more combinations were missing for subscription-manager parameters: %s" % str(e),
            )
