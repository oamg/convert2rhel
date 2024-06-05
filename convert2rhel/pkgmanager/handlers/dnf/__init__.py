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

from convert2rhel import exceptions, pkgmanager
from convert2rhel.pkghandler import get_system_packages_for_replacement
from convert2rhel.pkgmanager.handlers.base import TransactionHandlerBase
from convert2rhel.pkgmanager.handlers.dnf.callback import (
    DependencySolverProgressIndicatorCallback,
    PackageDownloadCallback,
    TransactionDisplayCallback,
)
from convert2rhel.systeminfo import system_info


loggerinst = logging.getLogger(__name__)
"""Instance of the logger used in this module."""


class DnfTransactionHandler(TransactionHandlerBase):
    """Implementation of the DNF transaction handler.

    This class will implement and override the public methods that comes from
    the abstractclass `TransactionHandlerBase`, with the intention to provide
    the defaults necessary for handling and processing the dnf transactions in
    the best way possible.

    _base: dnf.Base()
        The actual instance of the `dnf.Base()` class.
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
        """Create a new instance of the dnf.Base() class

        We create a new instance of the Base() inside this internal method
        with the intention of being able to re-initialize the base class
        whenever we need during the class workflow.

        .. note::
            Since we need have to delete the base class at the end of the
            `run_transaction` workflow so we can close the RPM database, preventing
            leaks or transaction mismatches between the validation and replacement
            of the packages, we use this internal method to make it easier to
            re-initialize it again.
        """
        self._base = pkgmanager.Base()
        self._base.conf.substitutions["releasever"] = system_info.releasever
        self._base.conf.module_platform_id = "platform:el" + str(system_info.version.major)
        # Keep the downloaded files after the transaction to prevent internet
        # issues in the second run of this class.
        # Ref: https://dnf.readthedocs.io/en/latest/conf_ref.html#keepcache-label
        self._base.conf.keepcache = True

        # Currently, the depsolver callback associated with `_ds_callback` is
        # just a bypass. We are overriding this property to use our own
        # depsolver callback, that will output useful information of what is
        # going in with the packages in the transaction.
        self._base._ds_callback = DependencySolverProgressIndicatorCallback()

        # Override the exclude option that is loaded from the config and set it
        # to empty.
        self._base.conf.substitutions["exclude"] = []

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
                # Order of commands based on DNF implementation of swap, different from YUM order:
                # https://github.com/rpm-software-management/dnf/blob/master/dnf/cli/commands/swap.py#L60
                self._base.install(pkg_spec=new_package)
                self._base.remove(pkg_spec=old_package)

    def _perform_operations(self):
        """Perform the necessary operations in the transaction.

        This internal method will actually perform three operations in the
        transaction: update, reinstall and downgrade. The downgrade
        will be executed only when the reinstall step raises
        `PackagesNotAvailableError`.
        """
        original_os_pkgs = get_system_packages_for_replacement()
        upgrades = self._base.sack.query().upgrades().latest()

        loggerinst.info("Adding %s packages to the dnf transaction set.", system_info.name)

        for pkg in original_os_pkgs:
            # Splitting the name and arch so we can filter it out in the list
            # of packages to upgrade.
            name, arch = tuple(pkg.rsplit(".", 1))
            upgrade_pkg = next(iter(upgrades.filter(name=name, arch=arch)), None)

            # If a package is marked for update, then we don't need to
            # proceed with reinstall, and possibly, the downgrade of this
            # package. This is an inconsistency that could lead to packages
            # being outdated in the system after the conversion.
            if upgrade_pkg:
                self._base.upgrade(pkg_spec=pkg)
                continue

            try:
                self._base.reinstall(pkg_spec=pkg)
            except pkgmanager.exceptions.PackagesNotAvailableError:
                try:
                    self._base.downgrade_to(pkg_spec=pkg, strict=True)
                except pkgmanager.exceptions.PackagesNotInstalledError:
                    loggerinst.warning("Package %s not available in RHEL repositories.", pkg)

        self._swap_base_os_specific_packages()

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
            loggerinst.critical_no_exit("Failed to resolve dependencies in the transaction.")
            raise exceptions.CriticalError(
                id_="FAILED_TO_RESOLVE_DEPENDENCIES",
                title="Failed to resolve dependencies.",
                description="During package transaction dnf failed to resolve the necessary dependencies needed for a package replacement.",
                diagnosis="Resolve dependencies failed with error %s." % (str(e)),
            )

        loggerinst.info("Downloading the packages that were added to the dnf transaction set.")
        try:
            self._base.download_packages(self._base.transaction.install_set, PackageDownloadCallback())
        except pkgmanager.exceptions.DownloadError as e:
            loggerinst.debug("Got the following exception message: %s" % e)
            loggerinst.critical_no_exit("Failed to download the transaction packages.")
            raise exceptions.CriticalError(
                id_="FAILED_TO_DOWNLOAD_TRANSACTION_PACKAGES",
                title="Failed to download packages in the transaction.",
                description="During package transaction dnf failed to download the necessary packages needed for the transaction.",
                diagnosis="Package download failed with error %s." % (str(e)),
            )

    def _process_transaction(self, validate_transaction):
        """Internal method that will process the transaction.

        :param validate_transaction: Determines if the transaction needs to be
        validated or not.
        :type validate_transaction: bool
        :raises SystemExit: If we can't process the transaction.
        """

        if validate_transaction:
            loggerinst.info("Validating the dnf transaction set, no modifications to the system will happen this time.")
            self._base.conf.tsflags.append("test")
        else:
            loggerinst.info("Replacing %s packages. This process may take some time to finish." % system_info.name)

        try:
            self._base.do_transaction(display=TransactionDisplayCallback())
        except (
            pkgmanager.exceptions.Error,
            pkgmanager.exceptions.TransactionCheckError,
        ) as e:
            loggerinst.debug("Got the following exception message: %s", e)
            loggerinst.critical_no_exit("Failed to validate the dnf transaction.")
            raise exceptions.CriticalError(
                id_="FAILED_TO_VALIDATE_TRANSACTION",
                title="Failed to validate dnf transaction.",
                description="During the dnf transaction execution an error occured and convert2rhel could no longer process the transaction.",
                diagnosis="Transaction processing failed with error: %s" % str(e),
            )

        if validate_transaction:
            loggerinst.info("Successfully validated the dnf transaction set.")
        else:
            loggerinst.info("System packages replaced successfully.")

    def run_transaction(self, validate_transaction=False):
        """Run the dnf transaction.

        Perform the transaction. If the `validate_transaction` parameter set to
        true, it means the transaction will not be executed, but rather verify
        everything and do an early return.

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
