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

from convert2rhel import actions, pkghandler
from convert2rhel.systeminfo import system_info


logger = logging.getLogger(__name__)


def _get_pkg_names(packages):
    return [pkghandler.get_pkg_nevra(pkg_obj, include_zero_epoch=True) for pkg_obj in packages]


class ListThirdPartyPackages(actions.Action):
    id = "LIST_THIRD_PARTY_PACKAGES"

    def run(self):
        """
        List packages not packaged by the original OS vendor or Red Hat and
        warn that these are not going to be converted.
        """
        super(ListThirdPartyPackages, self).run()

        logger.task("Convert: List third-party packages")
        third_party_pkgs = pkghandler.get_third_party_pkgs()
        if third_party_pkgs:
            pkg_list = pkghandler.format_pkg_info(sorted(third_party_pkgs, key=self.extract_packages))
            warning_message = (
                "Only packages signed by %s are to be"
                " replaced. Red Hat support won't be provided"
                " for the following third party packages:\n" % system_info.name
            )
            logger.warning(warning_message)
            logger.info(pkg_list)
            self.set_result(
                level="SUCCESS",
                id="THIRD_PARTY_PACKAGE_DETECTED",
            )
            self.add_message(
                level="WARNING",
                id="THIRD_PARTY_PACKAGE_DETECTED_MESSAGE",
                message=warning_message + ", ".join(_get_pkg_names(third_party_pkgs)),
            )
            return
        else:
            logger.info("No third party packages installed.")

    def extract_packages(self, pkg):
        """Key function to extract the package name from third_party_pkgs"""
        return pkg.nevra.name


class RemoveExcludedPackages(actions.Action):
    id = "REMOVE_EXCLUDED_PACKAGES"

    def run(self):
        """
        Certain packages need to be removed before the system conversion,
        depending on the system to be converted.
        """
        super(RemoveExcludedPackages, self).run()

        logger.task("Convert: Remove excluded packages")
        logger.info("Searching for the following excluded packages:\n")
        try:
            pkgs_to_remove = sorted(pkghandler._get_packages_to_remove(system_info.excluded_pkgs))
            pkgs_removed = sorted(pkghandler.remove_pkgs_unless_from_redhat(pkgs_to_remove))

            # TODO: Handling SystemExit here as way to speedup exception
            # handling and not refactor contents of the underlying function.
        except SystemExit as e:
            # TODO(r0x0d): Places where we raise SystemExit and need to be
            # changed to something more specific.
            #   - When we can't remove a package.
            self.set_result(level="ERROR", id="EXCLUDED_PACKAGE_REMOVAL_FAILED", message=str(e))
            return

        # shows which packages were not removed, if false, all packages were removed
        pkgs_not_removed = sorted(frozenset(pkgs_to_remove).difference(pkgs_removed))

        if pkgs_not_removed:
            pkg_names = _get_pkg_names(pkgs_not_removed)
            message = "The following packages were not removed: %s" % ", ".join(pkg_names)
            logger.warning(message)
            self.add_message(
                level="WARNING",
                id="EXCLUDED_PACKAGES_NOT_REMOVED",
                message=message,
            )
            return
        if pkgs_removed:
            message = "The following packages were removed: %s" % ", ".join(pkgs_removed)
            logger.info(message)
            self.add_message(
                level="INFO",
                id="EXCLUDED_PACKAGES_REMOVED",
                message=message,
            )
            return


class RemoveRepositoryFilesPackages(actions.Action):
    id = "REMOVE_REPOSITORY_FILES_PACKAGES"
    dependencies = ("BACKUP_REDHAT_RELEASE",)

    def run(self):
        """
        Remove those non-RHEL packages that contain YUM/DNF repofiles
        (/etc/yum.repos.d/*.repo) or affect variables in the repofiles (e.g.
        $releasever).

        Red Hat cannot automatically remove these non-RHEL packages with other
        excluded packages. While other excluded packages must be removed before
        installing subscription-manager to prevent package conflicts, these
        non-RHEL packages must be present on the system during
        subscription-manager installation so that the system can access and
        install subscription-manager dependencies. As a result, these non-RHEL
        packages must be manually removed after subscription-manager
        installation.
        """
        super(RemoveRepositoryFilesPackages, self).run()

        logger.task("Convert: Remove packages containing .repo files")
        logger.info("Searching for packages containing .repo files or affecting variables in the .repo files:\n")
        try:
            pkgs_to_remove = sorted(pkghandler._get_packages_to_remove(system_info.repofile_pkgs))
            pkgs_removed = sorted(pkghandler.remove_pkgs_unless_from_redhat(pkgs_to_remove))

            # TODO: Handling SystemExit here as way to speedup exception
            # handling and not refactor contents of the underlying function.
        except SystemExit as e:
            # TODO(r0x0d): Places where we raise SystemExit and need to be
            # changed to something more specific.
            #   - When we can't remove a package.
            self.set_result(level="ERROR", id="REPOSITORY_FILE_PACKAGE_REMOVAL_FAILED", message=str(e))
            return

        # shows which packages were not removed, if false, all packages were removed
        pkgs_not_removed = sorted(frozenset(pkgs_to_remove).difference(pkgs_removed))

        if pkgs_not_removed:
            pkg_names = _get_pkg_names(pkgs_not_removed)
            message = "The following packages were not removed: %s" % ", ".join(pkg_names)
            logger.warning(message)
            self.add_message(
                level="WARNING",
                id="REPOSITORY_FILE_PACKAGES_NOT_REMOVED",
                message=message,
            )
            return
        if pkgs_removed:
            message = "The following packages were removed: %s" % ", ".join(pkgs_removed)
            logger.info(message)
            self.add_message(
                level="INFO",
                id="REPOSITORY_FILE_PACKAGES_REMOVED",
                message=message,
            )
            return
