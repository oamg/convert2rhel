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

import logging
import os
import re

from convert2rhel import pkgmanager
from convert2rhel.backup import remove_pkgs
from convert2rhel.pkghandler import get_system_packages_for_replacement
from convert2rhel.pkgmanager.handlers.base import TransactionHandlerBase
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import BACKUP_DIR


loggerinst = logging.getLogger(__name__)

# Limit the number of yum transaction retries.
MAX_NUM_OF_ATTEMPTS_TO_RESOLVE_DEPS = 3

# Extract the first package that appears in the yum depsolve error
EXTRACT_PKG_FROM_YUM_DEPSOLVE = re.compile(r".*?(?=requires)")


def _resolve_yum_problematic_dependencies(output):
    """Internal function to parse yum resolve dependencies errors.

    This internal function has the purpose to parse the yum `resolveDeps()`
    errors that may arise from the transaction. It should not be used by other
    functions here, as the purpose of this is serving the yum single
    transactions.

    :param output: A list of strings with packages names that had a dependency
    error.
    :type output: list[str]
    """
    packages_to_remove = []
    if output:
        loggerinst.debug("Dependency resolution failed:\n- %s" % "\n- ".join(output))
    else:
        loggerinst.debug("Dependency resolution failed with no detailed message reported by yum.")
    for package in output:
        resolve_error = re.findall(EXTRACT_PKG_FROM_YUM_DEPSOLVE, str(package))
        if resolve_error:
            # The first string to appear in index 0 is the package we want.
            packages_to_remove.append(str(resolve_error[0]).replace(" ", ""))

    if packages_to_remove:
        packages_to_remove = set(packages_to_remove)
        loggerinst.debug(
            "Removing problematic packages to continue with the conversion:\n%s", "\n".join(packages_to_remove)
        )
        remove_pkgs(
            pkgs_to_remove=packages_to_remove,
            backup=True,
            critical=True,
            set_releasever=True,
            reposdir=BACKUP_DIR,
            custom_releasever=system_info.version.major,
            varsdir=os.path.join(BACKUP_DIR, "yum", "vars"),
        )

        loggerinst.debug("Finished backing up and removing the packages.")
    else:
        loggerinst.warning("Unable to resolve dependency issues.")


class YumTransactionHandler(TransactionHandlerBase):
    """Implementation of the YUM transaction handler.

    This class will implement and override the public methods that comes from
    the abstractclass `TransactionHandlerBase`, with the intention to provide
    the defaults necessary for handling and processing the yum transactions in
    the best way possible.

    _base: yum.YumBase()
        The actual instance of the `yum.YumBase()` class.
    _enabled_repos: list[str]
        A list of packages that are used during the transaction.
    """

    def __init__(self):
        # We are initializing the `_base` property here as `None`` and not with
        # `pkgmanager.YumBase()` because we need to re-initialize this property
        # every time we loop through the dependency solver, this way, avoiding
        # any caches by the `YumBase` that could cause some packages to not
        # being processed properly. Every time we need to process the transaction
        # (either by testing or actually consuming it), a new instance of this
        # class needs to be instantiated through the `_set_up_base()` private
        # method.
        self._base = None

    def _set_up_base(self):
        """Create a new instance of the yum.YumBase() class."""
        pkgmanager.misc.setup_locale(override_time=True)
        self._base = pkgmanager.YumBase()
        self._base.conf.yumvar["releasever"] = system_info.releasever

    def _enable_repos(self):
        """Enable a list of required repositories."""
        self._base.repos.disableRepo("*")
        enabled_repos = system_info.get_enabled_rhel_repos()
        loggerinst.info("Enabling RHEL repositories:\n%s" % "\n".join(enabled_repos))
        for repo in enabled_repos:
            self._base.repos.enableRepo(repo)

    def _perform_operations(self):
        """Perform the necessary operations in the transaction.

        This internal method will actually perform three operations in the
        transaction: downgrade, reinstall and downgrade. The downgrade only
        will be executed in case of the the reinstall step raises the
        `ReinstallInstallError`.
        """
        original_os_pkgs = get_system_packages_for_replacement()
        self._set_up_base()
        self._enable_repos()

        loggerinst.info("Adding %s packages to the yum transaction set.", system_info.name)

        for pkg in original_os_pkgs:
            self._base.update(pattern=pkg)
            try:
                self._base.reinstall(pattern=pkg)
            except (pkgmanager.Errors.ReinstallInstallError, pkgmanager.Errors.ReinstallRemoveError):
                try:
                    self._base.downgrade(pattern=pkg)
                except (
                    pkgmanager.Errors.ReinstallInstallError,
                    pkgmanager.Errors.ReinstallRemoveError,
                    pkgmanager.Errors.DowngradeError,
                ):
                    loggerinst.warning("Package %s not available in RHEL repositories.", pkg)

    def _resolve_dependencies(self, validate_transaction):
        """Try to resolve the transaction dependencies.

        This method will try to resolve the dependencies of the packages that
        are held in the transaction, we might need to call this internal method
        multiple times, that's why it's separated from the rest of the
        `_perform_operations()` internal method.

        .. notes::
            For YumBase().resolveDeps() the "exceptions" that can arise from this
            actually returns in the form of a tuple (int, str | list[str]),
            meaning that the error codes will have a different meaning and
            message depending on the number.
            For example:
              0. Transaction finished successfully, but it was empty.
              1. Any general error that happened during the transaction
              2. Transaction finished successfully, being able to process any
              package it had in the transaction set.

            We actually need to loop through this for some time to remove all the
            packages that are causing dependencies problems. This is stated in
            the yum source code for the `resolveDeps` function, that if any
            errors are "thrown" for the user, you will need to loop until the
            point you don't have any more errors.

        :return: A boolean indicating if it was successful or not.
        :rtype: bool
        """
        loggerinst.info("Resolving the dependencies of the packages in the yum transaction set.")
        ret_code, msg = self._base.resolveDeps()

        if ret_code == 1:
            # For the return code 1, yum can output two kinds of error, one being
            # that it reached the limit for depsolving, and the actual dependencies
            # that caused an problem.
            # If we reach the limit for depsolving, just return False.
            if "Depsolving loop limit reached" in msg:
                return False
            # If the message is the not the depsolving limit, then we need to
            # resolve the problematic dependencies.
            else:
                # We want to fail earlier in the process, so let's check for this
                # only when testing the transaction.
                if validate_transaction:
                    _resolve_yum_problematic_dependencies(msg)

                # Return False anyway because the depsolving failed.
                return False

        return True

    def _process_transaction(self, validate_transaction):
        """Internal method to process the transaction.

        :param validate_transaction: Determines if the transaction needs to be
        validated or not.
        :type validate_transaction: bool
        :raises SystemExit: If we can't process the transaction.
        """

        if validate_transaction:
            self._base.conf.tsflags.append("test")
            loggerinst.info("Validating the yum transaction set, no modifications to the system will happen this time.")
        else:
            loggerinst.info("Replacing %s packages. This process may take some time to finish." % system_info.name)

        try:
            self._base.processTransaction()
        except (
            pkgmanager.Errors.YumRPMCheckError,
            pkgmanager.Errors.YumTestTransactionError,
            pkgmanager.Errors.YumRPMTransError,
        ) as e:
            loggerinst.debug("Got the following exception message: %s", e)
            loggerinst.critical("Failed to validate the yum transaction.")

        if validate_transaction:
            loggerinst.info("Successfully validated the yum transaction set.")
        else:
            loggerinst.info("System packages replaced successfully.")

    def run_transaction(self, validate_transaction=False):
        """Run the yum transaction.

        This function is supposed to be an replacement of the old
        `call_yum_cmd_w_downgrades()` function, that in the past, used to call
        the yum commands (upgrade, reinstall and downgrade) several times in
        order to replace all the possible packages from the original system
        vendor to the RHEL ones.

        ..notes::
            The implementation of this yum transaction is different from the
            dnf one, mainly because yum can raise some "exceptions" while
            trying to resolve the dependencies of the transaction. Because of
            this, we need to loop through a couple of times until we know that
            all of the dependencies are resolved without problems.

            You might wonder "why not remove the packages that caused a
            failure and loop through the dep solving again?" Well. Since
            we are removing the problematic packages using `rpm` and not some
            specific method in the transaction itself, yum doesn't know that
            something has changed (The resolveDeps() function doesn't refresh
            if something else happens outside the transaction), in order to
            make sure that we won't have any problems with our transaction, it
            is easier to loop through everything again and just recreate the
            transaction, so yum will keep track of what's changed.

            This function should loop max 3 times to get to the point where our
            transaction doesn't have any problematic packages in there, and the
            subsequent transactions are "faster" because of some yum internal
            cache mechanism.

            This might be optimized in the future, but for now, it's somewhat
            reliable.

        :param vaidate_transaction: Determines if the transaction needs to be
        validated or not.
        :type valiate_transaction: bool
        :raises SystemExit: If we can't resolve the transaction dependencies.
        """
        resolve_deps_finished = False

        # Do not allow this to loop until eternity.
        attempts = 0
        while attempts <= MAX_NUM_OF_ATTEMPTS_TO_RESOLVE_DEPS:
            self._perform_operations()
            resolved = self._resolve_dependencies(validate_transaction)

            if not resolved:
                loggerinst.info("Retrying to resolve dependencies %s", attempts)
                attempts += 1
            else:
                resolve_deps_finished = True
                break

        if not resolve_deps_finished:
            loggerinst.critical("Failed to resolve dependencies in the transaction.")

        self._process_transaction(validate_transaction)

        # Because we call the same thing multiple times, the rpm database is
        # not properly closed at the end.
        # This cause problems because we have another special operation that
        # happen in the middle of all of this, that is preserving the rhel
        # kernel. In the YumBase() class there is a special __del__() method
        # that resolves all of the locks that it places during the transaction.
        del self._base
