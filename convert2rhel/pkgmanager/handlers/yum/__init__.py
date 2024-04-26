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
import logging
import os
import re

from convert2rhel import backup, exceptions, pkgmanager, utils
from convert2rhel.backup.packages import RestorablePackage
from convert2rhel.pkghandler import get_system_packages_for_replacement
from convert2rhel.pkgmanager.handlers.base import TransactionHandlerBase
from convert2rhel.pkgmanager.handlers.yum.callback import PackageDownloadCallback, TransactionDisplayCallback
from convert2rhel.repo import DEFAULT_YUM_VARS_DIR
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import remove_pkgs


loggerinst = logging.getLogger(__name__)
"""Instance of the logger used in this module."""

MAX_NUM_OF_ATTEMPTS_TO_RESOLVE_DEPS = 3
"""Limit the number of yum transaction retries."""

EXTRACT_PKG_FROM_YUM_DEPSOLVE = re.compile(r".*?(?=requires)")
"""Extract the first package that appears in the yum depsolve error."""


def _resolve_yum_problematic_dependencies(output):
    """Internal function to parse yum resolve dependencies errors.

    This internal function has the purpose to parse the yum `resolveDeps()`
    errors that may arise from the transaction. It should not be used by other
    functions here, as the purpose of this is serving the yum single
    transactions.

    :param output: A list of strings with packages names that had a dependency
    error.
    :type output: list[bytes]
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
            "Removing problematic packages to continue with the conversion:\n%s",
            "\n".join(packages_to_remove),
        )
        backedup_reposdir = backup.get_backedup_system_repos()
        backedup_yum_varsdir = os.path.join(backup.BACKUP_DIR, hashlib.md5(DEFAULT_YUM_VARS_DIR.encode()).hexdigest())

        backup.backup_control.push(
            RestorablePackage(
                pkgs=packages_to_remove,
                reposdir=backedup_reposdir,
                set_releasever=True,
                custom_releasever=system_info.version.major,
                varsdir=backedup_yum_varsdir,
            )
        )
        remove_pkgs(pkgs_to_remove=packages_to_remove, critical=True)

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

    def _close_yum_base(self):
        """Helper method to close the yum object.

        .. important::
            Because we call the same thing multiple times, the rpm database is
            not properly closed at the end of it, thus, having the need to call
            `self._base.close()` explicitly before we delete the object. If we
            use only `del self._base`, it seems that yum is not able to
            properly clean everything in the database.
        """
        self._base.close()
        del self._base

    def _set_up_base(self):
        """Create a new instance of the yum.YumBase() class

        We create a new instance of the YumBase() inside this internal method
        with the intention of being able to re-initialize the base class
        whenever we need during the class workflow.

        .. note::
            Since we need have to delete the base class at the end of the
            `run_transaction` workflow so we can close the RPM database, preventing
            leaks or transaction mismatches between the validation and replacement
            of the packages, we use this internal method to make it easier to
            re-initialize it again.
        """
        pkgmanager.misc.setup_locale(override_time=True)
        self._base = pkgmanager.YumBase()
        # Empty out the exclude list to avoid dependency problems during the
        # transaction validation.
        self._base.conf.exclude = []
        self._base.conf.yumvar["releasever"] = system_info.releasever

    def _enable_repos(self):
        """Enable a list of required repositories.

        :raises SystemInfo: If there is no way to connect to the mirrors in the
            repos.
        """
        self._base.repos.disableRepo("*")
        # Set the download progress display
        self._base.repos.setProgressBar(PackageDownloadCallback())
        enabled_repos = system_info.get_enabled_rhel_repos()
        loggerinst.info("Enabling RHEL repositories:\n%s" % "\n".join(enabled_repos))
        try:
            for repo in enabled_repos:
                self._base.repos.enableRepo(repo)
        except pkgmanager.Errors.RepoError as e:
            loggerinst.debug("Loading repository metadata failed: %s" % e)
            loggerinst.critical_no_exit("Failed to populate repository metadata.")
            raise exceptions.CriticalError(
                id_="FAILED_TO_ENABLE_REPOS",
                title="Failed to enable repositories.",
                description="We've encountered a failure when accessing repository metadata.",
                diagnosis="Loading repository metadata failed with error %s." % (str(e)),
            )

    def _swap_base_os_specific_packages(self):
        """Swap base os specific packages for their RHEL counterparts in the transaction.

        Some packages need to be manually injected in the transaction as a
        "swap", since those packages are not always able to be installed
        automatically by yum if they don't exist in the system anymore, this
        can cause problems during the transaction as missing dependencies.
        """
        # Related issue: https://issues.redhat.com/browse/RHELC-1130, see comments
        # to get more proper description of solution
        for old_package, new_package in system_info.swap_pkgs.items():
            loggerinst.debug("Checking if %s installed for later swap." % old_package)
            is_installed = system_info.is_rpm_installed(old_package)
            if is_installed:
                loggerinst.debug("Package %s will be swapped to %s during conversion." % (old_package, new_package))
                # Order of operations based on YUM implementation of swap:
                # https://github.com/rpm-software-management/yum/blob/master/yumcommands.py#L3488
                self._base.remove(pattern=old_package)
                self._base.install(pattern=new_package)

    def _perform_operations(self):
        """Perform the necessary operations in the transaction.

        This internal method will actually perform three operations in the
        transaction: downgrade, reinstall and downgrade. The downgrade only
        will be executed in case of the the reinstall step raises the
        `ReinstallInstallError`.
        """
        original_os_pkgs = get_system_packages_for_replacement()
        self._enable_repos()

        loggerinst.info("Adding %s packages to the yum transaction set.", system_info.name)

        try:
            for pkg in original_os_pkgs:
                can_update = self._base.update(pattern=pkg)

                # If a package is marked for update, then we don't need to
                # proceed with reinstall, and possibly, the downgrade of this
                # package. This is an inconsistency that could lead to packages
                # being outdated in the system after the conversion.
                if can_update:
                    continue
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

            # Swapping the packages needs to be after the operations
            # If not, swapped packages are removed from transaction as obsolete
            self._swap_base_os_specific_packages()
        except pkgmanager.Errors.NoMoreMirrorsRepoError as e:
            loggerinst.debug("Got the following exception message: %s", e)
            loggerinst.critical_no_exit("There are no suitable mirrors available for the loaded repositories.")
            raise exceptions.CriticalError(
                id_="FAILED_TO_LOAD_REPOSITORIES",
                title="Failed to find suitable mirrors for the load repositories.",
                description="All available mirrors were tried and none were available.",
                diagnosis="Repository mirrors failed with error %s." % (str(e)),
            )

    def _resolve_dependencies(self):
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

        :return: If the base.resolveDeps() method returns a message, we will
            return that message, otherwise, return None.
        :rtype: str | None
        """
        loggerinst.info("Resolving the dependencies of the packages in the yum transaction set.")
        ret_code, msg = self._base.resolveDeps()

        if ret_code == 1:
            return msg

        return None

    def _process_transaction(self, validate_transaction):
        """Internal method to process the transaction.

        :param validate_transaction: Determines if the transaction needs to be
            validated or not.
        :type validate_transaction: bool
        :raises SystemExit: If we can't process the transaction.
        """

        if validate_transaction:
            self._base.conf.tsflags.append("test")
            loggerinst.info(
                "Downloading and validating the yum transaction set, no modifications to the system will happen "
                "this time."
            )
        else:
            loggerinst.info(
                "Replacing %s packages. This process may take some time to finish.",
                system_info.name,
            )

        try:
            self._base.processTransaction(
                rpmDisplay=TransactionDisplayCallback(),
            )
        except pkgmanager.Errors.YumBaseError as e:
            # We are catching only `pkgmanager.Errors.YumBaseError` as the base
            # exception here because all of the other exceptions that can be
            # raised during the transaction process inherit it from
            # YumBaseError.

            # The following exceptions is the ones we are actually looking for,
            # but simplified to only catch the YumBaseError:
            #  - pkgmanager.Errors.YumRPMCheckError
            #  - pkgmanager.Errors.YumTestTransactionError
            #  - pkgmanager.Errors.YumRPMTransError
            #  - pkgmanager.Errors.YumDownloadError
            #  - pkgmanager.Errors.YumBaseError
            #  - pkgmanager.Errors.YumGPGCheckError
            loggerinst.debug("Got the following exception message: %s", e)
            loggerinst.critical_no_exit("Failed to validate the yum transaction.")
            raise exceptions.CriticalError(
                id_="FAILED_TO_VALIDATE_TRANSACTION",
                title="Failed to validate yum transaction.",
                description="During the yum transaction execution an error occurred and convert2rhel could no longer process the transaction.",
                diagnosis="Transaction processing failed with error %s." % (" ".join(e)),
            )

        if validate_transaction:
            loggerinst.info("Successfully validated the yum transaction set.")
        else:
            loggerinst.info("System packages replaced successfully.")

    def run_transaction(self, validate_transaction=False):
        """Run the yum transaction.

        Perform the transaction. If the `validate_transaction` parameter set to
        true, it means the transaction will not be executed, but rather verify
        everything and do an early return.

        :param validate_transaction: Determines if the transaction needs to be
            validated or not.
        :type validate_transaction: bool
        :raises CriticalError: If we can't resolve the transaction dependencies.
        """
        resolve_deps_finished = False
        # Do not allow this to loop until eternity.
        attempts = 0
        try:
            while attempts <= MAX_NUM_OF_ATTEMPTS_TO_RESOLVE_DEPS:
                self._set_up_base()
                messages = self._run_transaction_subprocess(validate_transaction)
                if messages:
                    if "Depsolving loop limit reached" not in messages and validate_transaction:
                        _resolve_yum_problematic_dependencies(messages)

                    loggerinst.info("Retrying to resolve dependencies %s", attempts)
                    attempts += 1
                else:
                    resolve_deps_finished = True
                    break

            if not resolve_deps_finished:
                loggerinst.critical_no_exit("Failed to resolve dependencies in the transaction.")
                raise exceptions.CriticalError(
                    id_="FAILED_TO_RESOLVE_DEPENDENCIES",
                    title="Failed to resolve dependencies.",
                    description="During package transaction yum failed to resolve the necessary dependencies needed for a package replacement.",
                )
        finally:
            self._close_yum_base()

    @utils.run_as_child_process
    def _run_transaction_subprocess(self, validate_transaction):
        """Run the necessary transaction operations under a subprocess.

        .. important::
            This function is being executed in a child process so we will be
            able to raise SIGINT or any other signal that is sent to the main
            process.

            The function calls here do not affect the others subprocess calls
            that are called after this function during the conversion, but, it
            does affect the signal handling while the user tries to send that
            signal while this function is executing.

        ..notes::
            The implementation of this yum transaction is different from the
            dnf one, mainly because yum can raise some "exceptions" while
            trying to resolve the dependencies of the transaction. Because of
            this, we need to loop through a couple of times until we know that
            all of the dependencies are resolved without problems.

            You might wonder "why not remove the packages that caused a failure
            and loop through the dep solving again?" Well. Since we are
            removing the problematic packages using `rpm` and not some specific
            method in the transaction itself, yum doesn't know that something
            has changed (The resolveDeps() function doesn't refresh if
            something else happens outside the transaction), in order to make
            sure that we won't have any problems with our transaction, it is
            easier to loop through everything again and just recreate the
            transaction, so yum will keep track of what's changed.

            This function should loop max 3 times to get to the point where our
            transaction doesn't have any problematic packages in there, and the
            subsequent transactions are "faster" because of some yum internal
            cache mechanism.

            This might be optimized in the future, but for now, it's somewhat
            reliable.

        :param vaidate_transaction: Determines if the transaction needs to be
            validated or not.
        :type validate_transaction: bool
        :returns str | None: If any messages are raised from the dependency
            resolve methods, we return that to the caller. Otherwise, we return
            None.
        """
        self._perform_operations()
        messages = self._resolve_dependencies()

        if not messages:
            self._process_transaction(validate_transaction)

        return messages
