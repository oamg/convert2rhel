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

import logging

from convert2rhel import pkgmanager
from convert2rhel.pkghandler import get_system_packages_for_replacement
from convert2rhel.pkgmanager.handlers.base import TransactionHandlerBase
from convert2rhel.systeminfo import system_info


loggerinst = logging.getLogger(__name__)


class DnfTransactionHandler(TransactionHandlerBase):
    """Implementation of the DNF transaction handler.

    This class will implement and override the public methods that comes from
    the abstractclass `TransactionHandlerBase`, with the intention to provide
    the defaults necessary for handling and processing the dnf transactions in
    the best way possible.

    _base: dnf.Base()
        The actual instance of the `dnf.Base()` class.
    _enabled_repos: list[str]
        A list of packages that are used during the transaction.
    """

    def __init__(self):
        # We are initializing the `_base` property here as `None` and not with
        # `pkgmanager.Base()` because we split the usage of this class into
        # two phases that are mostly identitical.
        # - The first phase is where we validate that the dnf transaction will
        # pass and resolve any dependencies that are required by the packages
        # and not break the system after the PONR.
        # - The second phase, being the last one, is where we actually let the
        # dnf transaction to be processed and change the packages (i.e:
        # reinstall, upgrade, downgrade, ...).
        self._base = None

    def _set_up_base(self):
        """Create a new instance of the dnf.Base() class."""
        self._base = pkgmanager.Base()
        self._base.conf.substitutions["releasever"] = system_info.releasever
        self._base.conf.module_platform_id = "platform:el8"

        # Keep the downloaded files after the transaction to prevent internet
        # issues in the second run of this class.
        # Ref: https://dnf.readthedocs.io/en/latest/conf_ref.html#keepcache-label
        self._base.conf.keepcache = True

    def _enable_repos(self):
        """Enable a list of required repositories."""
        self._base.read_all_repos()
        repos = self._base.repos.all()
        enabled_repos = system_info.get_enabled_rhel_repos()
        loggerinst.info("Enabling RHEL repositories:\n%s" % "\n".join(enabled_repos))
        try:
            for repo in repos:
                # Disable the repositories that we don't want if the `repo.id`
                # is not in the `enabled_repos` list, otherwise explicitly enable it
                # to make sure that it will be available when we run the transactions.
                repo.disable() if repo.id not in enabled_repos else repo.enable()

            # Load metadata of the enabled repositories
            self._base.fill_sack()
        except pkgmanager.exceptions.RepoError as e:
            loggerinst.debug("Loading repository metadata failed: %s" % e)
            loggerinst.critical("Failed to populate repository metadata.")

    def _perform_operations(self):
        """Perform the necessary operations in the transaction.

        This internal method will actually perform three operations in the
        transaction: update, reinstall and downgrade. The downgrade
        will be executed only when the reinstall step raises
        `PackagesNotAvailableError`.
        """
        original_os_pkgs = get_system_packages_for_replacement()

        loggerinst.info("Adding %s packages to the dnf transaction set.", system_info.name)

        for pkg in original_os_pkgs:
            self._base.upgrade(pkg_spec=pkg)
            try:
                self._base.reinstall(pkg_spec=pkg)
            except pkgmanager.exceptions.PackagesNotAvailableError:
                try:
                    self._base.downgrade(pkg_spec=pkg)
                except pkgmanager.exceptions.PackagesNotInstalledError:
                    loggerinst.warning("Package %s not available in RHEL repositories.", pkg)

    def _resolve_dependencies(self):
        """Resolve the dependencies for the transaction.

        This internal method is meant to handle the resolvement of the
        transaction, including the step to download the packages that are used
        in the replacement.

        :raises SystemExit: If we fail to resolve the dependencies or
            downloading the packages.
        """
        loggerinst.info("Resolving the dependencies of the packages in the dnf transaction set.")
        try:
            self._base.resolve(allow_erasing=True)
        except pkgmanager.exceptions.DepsolveError as e:
            loggerinst.debug("Got the following exception message: %s" % e)
            loggerinst.critical("Failed to resolve dependencies in the transaction.")

        loggerinst.info("Downloading the packages that were added to the dnf transaction set.")
        try:
            self._base.download_packages(self._base.transaction.install_set)
        except pkgmanager.exceptions.DownloadError as e:
            loggerinst.debug("Got the following exception message: %s" % e)
            loggerinst.critical("Failed to download the transaction packages.")

    def _process_transaction(self, validate_transaction):
        """Internal method that will process the transaction.

        :param validate_transaction: Determines if the transaction needs to be
        validated or not.
        :type validate_transaction: bool
        :raises SystemExit: If we can't process the transaction.
        """

        if validate_transaction:
            self._base.conf.tsflags.append("test")
            loggerinst.info("Validating the dnf transaction set, no modifications to the system will happen this time.")
        else:
            loggerinst.info("Replacing %s packages. This process may take some time to finish." % system_info.name)

        try:
            self._base.do_transaction()
        except (
            pkgmanager.exceptions.Error,
            pkgmanager.exceptions.TransactionCheckError,
        ) as e:
            loggerinst.debug("Got the following exception message: %s", e)
            loggerinst.critical("Failed to validate the dnf transaction.")

        if validate_transaction:
            loggerinst.info("Successfully validated the dnf transaction set.")
        else:
            loggerinst.info("System packages replaced successfully.")

    def run_transaction(self, validate_transaction=False):
        """Run the dnf transaction.

        Perform the transaction. If the `validate_transaction` parameter set to
        true, it means the transaction will not be executed, but rather verify everything
        and do an early return.

        :param validate_transaction: Determines if the transaction needs to be
        validated or not.
        :type validate_transaction: bool
        :raises SystemExit: If there was any problem during the
        """
        self._set_up_base()
        self._enable_repos()

        self._perform_operations()
        self._resolve_dependencies()
        self._process_transaction(validate_transaction)

        # Because we call the same thing multiple times, the rpm database is not
        # properly closed at the end of it, thus, having the need to call
        # `self._base.close()` explicitly before we delete the object. If we use
        # only `del self._base`, it seems that dnf is not able to properly clean
        # everything in the database. We were seeing some problems in the next
        # steps with the rpmdb, as the history had changed.
        self._base.close()
        del self._base
