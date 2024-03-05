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
import os.path

from convert2rhel import actions, backup, exceptions, pkghandler, repo, subscription, toolopts, utils
from convert2rhel.backup.certs import RestorablePEMCert


logger = logging.getLogger(__name__)

# Source and target directories for the cdn.redhat.com domain ssl ca cert that:
# - we tell customers to use when installing convert2rhel from that domain
# - is used by RHSM when accessing RHEL repos hosted on the Red Hat CDN
_REDHAT_CDN_CACERT_SOURCE_DIR = utils.DATA_DIR
_REDHAT_CDN_CACERT_TARGET_DIR = "/etc/rhsm/ca/"

# Source and target directories for the RHSM ssl cert that we tell customers need
# to use to access repositories managed by subscription-manager
_RHSM_PRODUCT_CERT_SOURCE_DIR = os.path.join(utils.DATA_DIR, "rhel-certs")
_RHSM_PRODUCT_CERT_TARGET_DIR = "/etc/pki/product-default"


class InstallRedHatCertForYumRepositories(actions.Action):
    id = "INSTALL_RED_HAT_CERT_FOR_YUM"

    def run(self):
        super(InstallRedHatCertForYumRepositories, self).run()

        # We need to make sure the redhat-uep.pem file exists since the
        # various Red Hat yum repositories (including the convert2rhel
        # repo) use it.
        # The subscription-manager-rhsm-certificates package contains this cert but for
        # example on CentOS Linux 7 this package is missing the cert due to intentional
        # debranding. Thus we need to ensure the cert is in place even when the pkg is installed.
        logger.task("Convert: Install cdn.redhat.com SSL CA certificate")
        repo_cert = RestorablePEMCert(_REDHAT_CDN_CACERT_SOURCE_DIR, _REDHAT_CDN_CACERT_TARGET_DIR)
        backup.backup_control.push(repo_cert)


class InstallRedHatGpgKeyForRpm(actions.Action):
    id = "INSTALL_RED_HAT_GPG_KEY"

    def run(self):
        super(InstallRedHatGpgKeyForRpm, self).run()

        # Import the Red Hat GPG Keys for installing Subscription-manager
        # and for later.
        logger.task("Convert: Import Red Hat GPG keys")
        pkghandler.install_gpg_keys()


class PreSubscription(actions.Action):
    id = "PRE_SUBSCRIPTION"
    dependencies = (
        "REMOVE_SPECIAL_PACKAGES",
        "INSTALL_RED_HAT_CERT_FOR_YUM",
        "INSTALL_RED_HAT_GPG_KEY",
    )

    def run(self):
        super(PreSubscription, self).run()

        if toolopts.tool_opts.no_rhsm:
            # Note: we don't use subscription.should_subscribe here because we
            # need the subscription-manager packages even if we don't subscribe
            # the system.  It's only if --no-rhsm is passed (so we rely on
            # user configured repos rather than system-manager configured repos
            # to get RHEL packages) that we do not need subscription-manager
            # packages.
            logger.warning("Detected --no-rhsm option. Did not perform the check.")
            self.add_message(
                level="WARNING",
                id="PRE_SUBSCRIPTION_CHECK_SKIP",
                title="Pre-subscription check skip",
                description="Detected --no-rhsm option. Did not perform the check.",
            )
            return

        try:
            logger.task("Convert: Subscription Manager - Check for installed packages")
            subscription_manager_pkgs = subscription.needed_subscription_manager_pkgs()
            if not subscription_manager_pkgs:
                logger.info("Subscription Manager is already present")
            else:
                logger.task("Convert: Subscription Manager - Install packages")
                # Hack for 1.4: if we install subscription-manager from the UBI repo, it
                # may require newer versions of packages than provided by the vendor.
                # (Note: the function is marked private because this is a hack
                # that should be replaced when we aren't under a release
                # deadline.
                update_pkgs = subscription._dependencies_to_update(subscription_manager_pkgs)

                # Part of another hack for 1.4 that allows us to rollback part
                # of the backup control, then do old rollback items that
                # haven't been ported into the backup framework yet, and then
                # do the rest.
                # We need to do this here so that subscription-manager packages
                # that we install are uninstalled before other packages which
                # we may install during rollback.
                backup.backup_control.push(backup.backup_control.partition)

                subscription.install_rhel_subscription_manager(subscription_manager_pkgs, update_pkgs)

            logger.task("Convert: Subscription Manager - Verify installation")
            subscription.verify_rhsm_installed()

            logger.task("Convert: Install a RHEL product certificate for RHSM")
            product_cert = RestorablePEMCert(_RHSM_PRODUCT_CERT_SOURCE_DIR, _RHSM_PRODUCT_CERT_TARGET_DIR)
            backup.backup_control.push(product_cert)

        except SystemExit as e:
            # This should not occur anymore as all the relevant SystemExits has been changed to a CriticalError
            # exception. This exception handler is just a precaution
            self.set_result(
                level="ERROR",
                id="UNKNOWN_ERROR",
                title="Unknown error",
                description="The cause of this error is unknown, please look at the diagnosis for more information.",
                diagnosis=str(e),
            )
        except exceptions.CriticalError as e:
            self.set_result(
                level="ERROR",
                id=e.id,
                title=e.title,
                description=e.description,
                diagnosis=e.diagnosis,
                remediations=e.remediations,
                variables=e.variables,
            )
        except subscription.UnregisterError as e:
            self.set_result(
                level="ERROR",
                id="UNABLE_TO_REGISTER",
                title="System unregistration failure",
                description="The system is already registered with subscription-manager even though it is running CentOS not RHEL. We have failed to remove that registration.",
                diagnosis="Failed to unregister the system: %s" % e,
                remediations="You may want to unregister the system manually and re-run convert2rhel.",
            )


class SubscribeSystem(actions.Action):
    id = "SUBSCRIBE_SYSTEM"
    dependencies = (
        # Implicit dependency for `BACKUP_REDHAT_RELEASE`
        "PRE_SUBSCRIPTION",
        "EUS_SYSTEM_CHECK",
    )

    def run(self):
        super(SubscribeSystem, self).run()

        if not subscription.should_subscribe():
            if toolopts.tool_opts.no_rhsm:
                logger.warning("Detected --no-rhsm option. Did not perform subscription step.")
                self.add_message(
                    level="WARNING",
                    id="SUBSCRIPTION_CHECK_SKIP",
                    title="Subscription check skip",
                    description="Detected --no-rhsm option. Did not perform the check.",
                )
                return

            logger.task("Convert: Subscription Manager - Reload configuration")
            # We will use subscription-manager later to enable the RHEL repos so we need to make
            # sure subscription-manager knows about the product certificate. Refreshing
            # subscription info will do that.
            try:
                subscription.refresh_subscription_info()
            except subscription.RefreshSubscriptionManagerError as e:
                if "not yet registered" in str(e):
                    self.set_result(
                        level="ERROR",
                        id="SYSTEM_NOT_REGISTERED",
                        title="Not registered with RHSM",
                        description="This system must be registered with rhsm in order to get access to the RHEL rpms. In this case, the system was not already registered and no credentials were given to convert2rhel to register it.",
                        remediations="You may either register this system via subscription-manager before running convert2rhel or give convert2rhel credentials to do that for you. The credentials convert2rhel would need are either activation_key and organization or username and password. You can set these in a config file and then pass the file to convert2rhel with the --config-file option.",
                    )
                    return
                raise

            logger.warning("No rhsm credentials given to subscribe the system. Did not perform the subscription step.")

        try:
            # In the future, refactor this to be an else on the previous
            # condition or a separate Action.  Not doing it now because we
            # have to disentangle the exception handling when we do that.
            if subscription.should_subscribe():
                logger.task("Convert: Subscription Manager - Subscribe system")
                restorable_subscription = subscription.RestorableSystemSubscription()
                backup.backup_control.push(restorable_subscription)

            logger.task("Convert: Get RHEL repository IDs")
            rhel_repoids = repo.get_rhel_repoids()

            logger.task("Convert: Subscription Manager - Disable all repositories")
            subscription.disable_repos()

            # we need to enable repos after removing repofile pkgs, otherwise
            # we don't get backups to restore from on a rollback
            logger.task("Convert: Subscription Manager - Enable RHEL repositories")
            subscription.enable_repos(rhel_repoids)
        except OSError as e:
            # This should not occur anymore as all the relevant OSError has been changed to a CriticalError
            # exception. This exception handler is just a precaution
            self.set_result(
                level="ERROR",
                id="MISSING_SUBSCRIPTION_MANAGER_BINARY",
                title="Missing subscription-manager binary",
                description="There is a missing subscription-manager binary",
                diagnosis="Failed to execute command: %s" % e,
            )
        except exceptions.CriticalError as e:
            self.set_result(
                level="ERROR",
                id=e.id,
                title=e.title,
                description=e.description,
                diagnosis=e.diagnosis,
                remediations=e.remediations,
                variables=e.variables,
            )
        except SystemExit as e:
            # This should not occur anymore as all the relevant SystemExits has been changed to a CriticalError
            # exception. This exception handler is just a precaution
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
