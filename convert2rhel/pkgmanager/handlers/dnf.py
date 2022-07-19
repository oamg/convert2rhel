import logging

from convert2rhel import pkgmanager
from convert2rhel.backup import remove_pkgs
from convert2rhel.pkghandler import get_system_packages_for_replacement
from convert2rhel.pkgmanager.handlers.base import TransactionHandlerBase
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import BACKUP_DIR


loggerinst = logging.getLogger(__name__)


class DnfTransactionHandler(TransactionHandlerBase):
    """Implementation of the DNF transaction handler.

    This class will implement and override the public methods that comes from
    the abstractclass `TransactionHandlerBase`, whith the intention to provide
    the defaults necessary for handling and processing the dnf transactions in
    the best way possible.

    _base: dnf.Base()
        The actual instance of the `dnf.Base()` class.
    _enabled_repos: list[str]
        A list of packages that are used during the transaction.
    """

    def __init__(self):
        self._base = None
        self._enabled_repos = system_info.get_enabled_rhel_repos()

    def _setup_base(self):
        """Create a new instance of the dnf.Base() class."""
        self._base = pkgmanager.Base()
        self._base.conf.substitutions["releasever"] = system_info.releasever
        self._base.conf.module_platform_id = "platform:el8"

    def _enable_repos(self):
        """Enable a list of required repositories."""
        # Read and populate the repositories class in DNF
        self._base.read_all_repos()
        repos = self._base.repos.all()
        for repo in repos:
            # We are disabling the repositories that we don't want based on
            # this `if` condition were if the repo.id is not in the
            # enabled_repos list, we just disable it. In the other hand, if it
            # is a repo that we want to have enabled, let's just call
            # repo.enable() to make sure that it will be enabled when we run
            # the transactions.
            repo.disable if repo.id not in self._enabled_repos else repo.enable()

        # Fill the sack for the enabled repositories
        self._base.fill_sack()

    def _perform_operations(self):
        """Perform the necessary operations in the transaction.

        This internal method will actually perform three operations in the
        transaction: downgrade, reinstall and downgrade. The downgrade only
        will be eecuted in case of the the reinstall step raises the
        `PackagesNotAvailableError`.

        :raises SystemExit: In case of the dependency solving fails.
        """
        original_os_pkgs = get_system_packages_for_replacement()
        loggerinst.info("Performing upgrade, reinstall and downgrade of the %s packages ..." % system_info.name)
        for pkg in original_os_pkgs:
            self._base.upgrade(pkg_spec=pkg)
            try:
                self._base.reinstall(pkg_spec=pkg)
            except pkgmanager.exceptions.PackagesNotAvailableError:
                try:
                    self._base.downgrade(pkg)
                except pkgmanager.exceptions.PackagesNotInstalledError:
                    loggerinst.warning("Package %s not available for downgrade.", pkg)
                    remove_pkgs(
                        pkgs_to_remove=[pkg],
                        backup=True,
                        critical=False,
                        reposdir=BACKUP_DIR,
                        set_releasever=False,
                        manual_releasever=system_info.version.major,
                    )

        # Resolve, donwload and process the transaction
        try:
            self._base.resolve(allow_erasing=True)
        except pkgmanager.exceptions.DepsolveError as e:
            loggerinst.critical("Failed to resolve dependencies in the transaction.")
            loggerinst.debug("Got the following exception message: %s" % e)

        try:
            self._base.download_packages(self._base.transaction.install_set)
        except pkgmanager.exceptions.DownloadError as e:
            loggerinst.critical("An exception raised during the download packages.")
            loggerinst.debug("Got the following exception message: %s" % e)

    def _process_transaction(self):
        """Internal method that will process the transaction.

        :raises SystemExit: If there is any transaction error that was not
        handled properly.
        """
        try:
            self._base.do_transaction()
        except (
            pkgmanager.exceptions.Error,
            pkgmanager.exceptions.TransactionCheckError,
        ) as e:
            loggerinst.critical("An exception raised during the transaction.")
            loggerinst.debug("Got the following exception message: %s" % e)

        loggerinst.info("Finished processing the transaction.")

    def process_transaction(self, test_transaction=False):
        """Process the dnf transaction.

        In this method, we will try to perform the transaction based on a
        conditional statement that will toggle the transaction test or not.
        If we need to toggle the transaction test, we then append the "test"
        flag to the `tsflags` property in the base class, which will not
        consume the transaction, but rather, test everytyhing and do an early
        return. Otherwise, if we have the `test_transaction` paramter set to
        false, it indicates that we actually want to process the transaction
        and consume it (The test will happen anyway, but this should pass
        without problems).

        :param test_transaction: Determines if the transaction needs to be
        tested or not.
        :type test_transaction: bool
        """
        self._setup_base()
        self._enable_repos()

        self._perform_operations()

        # If we need to verify the transaction the first time, we need to
        # append the "test" flag to the `tsflags`.
        if test_transaction:
            self._base.conf.tsflags.append("test")
            loggerinst.info("Testing the dnf transaction before the replacement.")
        else:
            loggerinst.info("Replacing the system packages.")

        self._process_transaction()
