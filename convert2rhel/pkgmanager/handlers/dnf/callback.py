# -*- coding: utf-8 -*-
#
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
#
# This file incorporates work covered by the following copyrights and
# permission notices:
#
# Copyright (C) 2013-2016 Red Hat, Inc.
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# the GNU General Public License v.2, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY expressed or implied, including the implied warranties of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.  You should have received a copy of the
# GNU General Public License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.  Any Red Hat trademarks that are incorporated in the
# source code or documentation are not subject to the GNU General Public
# License and may only be used or replicated with the express permission of
# Red Hat, Inc.
#
#   License above taken from the original code at:
#
#       https://github.com/rpm-software-management/dnf/blob/4.7.0/dnf/cli/progress.py
#
# Copyright 2005 Duke University
# Copyright (C) 2012-2016 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
#   License above taken from the original code at:
#
#       https://github.com/rpm-software-management/dnf/blob/4.7.0/dnf/cli/output.py
import logging

from convert2rhel import pkgmanager


loggerinst = logging.getLogger(__name__)
"""Instance of the logger used in this module."""


class DependencySolverProgressIndicatorCallback(pkgmanager.Depsolve):
    """Depedency Solver callback to inform the user about the resolutions in the transaction."""

    _DEPSOLVE_MODES = {
        "i": "%s will be installed.",
        "u": "%s will be an update.",
        "e": "%s will be erased.",
        "r": "%s will be reinstalled.",
        "d": "%s will be an downgrade.",
        "o": "%s will obsolete another package.",
        "ud": "%s will be updated.",
        "od": "%s will be obsoleted.",
    }
    """A mapping of the different modes and the required message to be used."""

    def pkg_added(self, pkg, mode):
        """Output a message of the package added to the dependency solver.

        This method has the purpose of sending a message that indicates what the
        package added to the dependency solver transaction will be doing.

        :param pkg: The package itself added to the dependency solver. It's is
            composable of `name`, `arch`, `version` and `repository`.
        :type pkg: dnf.package.Package
        :param mode: The mode that will be performed by the package.
        :type mode: str
        """
        try:
            message = self._DEPSOLVE_MODES[mode]
        except KeyError:
            message = None
            loggerinst.debug("Unknow operation (%s) for package '%s'." % (mode, pkg))

        if message:
            loggerinst.info(message, pkg)

    def start(self):
        """Handle the beginning of the dependency resolution process."""
        loggerinst.info("Starting dependency resolution process.")

    def end(self):
        """Handle the end of the dependency resolution process."""
        loggerinst.info("Finished dependency resolution process.")


class PackageDownloadCallback(pkgmanager.DownloadProgress):
    """Package download callback for DNF transaction."""

    _STATUS_MAPPING = {
        pkgmanager.callback.STATUS_FAILED: "FAILED",
        pkgmanager.callback.STATUS_ALREADY_EXISTS: "SKIPPED",
        pkgmanager.callback.STATUS_MIRROR: "MIRROR",
        pkgmanager.callback.STATUS_DRPM: "DRPM",
    }
    """A mapping of the packages download status to a more formal string representation."""

    def __init__(self):
        """Constructor for the package download progress indicator.

        We initialize a few properties here for keeping track of progression of
        the downloaded files.
        """
        self.total_drpm = 0
        self.done_drpm = 0
        self.total_files = 0
        self.total_size = 0
        self.done_files = 0
        self.done_size = 0

    def start(self, total_files, total_size, total_drpms=0):
        """Indicate that a new progress metering started.

        In this method, we populate and upadte a few properties of this class
        with the information that is sent from the DNF API. This method is vital
        if we want to keep the tracking of how many needs to be processed.

        :param total_files: The total amount of files that will be downloaded.
        :type total_files: int
        :param total_size: The sum of all files downloaded.
        :type total_size: int
        :param total_drpms: The total of DRPMS that will be downloaded.
        :type total_drpms: int
        """
        self.total_files = total_files
        self.total_size = total_size
        self.total_drpm = total_drpms

    def end(self, payload, status, err_msg):
        """Communicate the information that `payload` has finished downloading.

        ..note::
            DNF will give us an status to the file that is being downloaded, so
            we can print this status to the user, as a way of them knowing that
            the file was skipped due a cache or any other status.

        :param payload: The payload snet in the callback.
        :type payload: dnf.repo.RPMPayload
        :param status: A constant denoting the type of outcome.
        :type status: int
        :param err_msg: An error message in case the outcome was an error
        :type err_msg: str
        """
        package = pkgmanager.pycomp.unicode(payload)
        size = int(payload.download_size)

        if status == pkgmanager.callback.STATUS_MIRROR:
            pass
        elif status == pkgmanager.callback.STATUS_DRPM:
            self.done_drpm += 1
        else:
            self.done_files += 1
            self.done_size += size

        if status:
            # the error message, no trimming
            if status is pkgmanager.callback.STATUS_DRPM and self.total_drpm > 1:
                msg = "(%d/%d) [%s %d/%d]: %s" % (
                    self.done_files,
                    self.total_files,
                    self._STATUS_MAPPING[status],
                    self.done_drpm,
                    self.total_drpm,
                    package,
                )
                msg = "%s - %s" % (msg, err_msg)
            else:
                msg = "(%d/%d) [%s]: %s" % (
                    self.done_files,
                    self.total_files,
                    self._STATUS_MAPPING.get(status, "Unknow"),
                    package,
                )
        else:
            if self.total_files > 1:
                msg = "(%d/%d): %s" % (self.done_files, self.total_files, package)

        loggerinst.info(msg)


class TransactionDisplayCallback(pkgmanager.TransactionDisplay):
    """Transaction display callback for DNF transaction."""

    def __init__(self):
        """Constructor for the transaction display progress in DNF."""
        super(TransactionDisplayCallback, self).__init__()
        self.last_package_seen = None
        self.output = True

    def progress(self, package, action, ti_done, ti_total, ts_done, ts_total):
        """Process and output the RPM operations in the transaction.

        :param package: Package being processed in the transaction.
        :type package: `dnf.package.Package`
        :param action: The type of the action being used for the current
            `package`. Only values that came from :func:`rpmtrans.TransactionDisplay.action.keys()` are valid.
        :type action: int
        :param ti_done: How much work was already been done in the transaction.
        :type ti_done: int
        :param ti_total: How much work in total is present in the transaction.
        :type ti_total: int
        :param ts_done: Number, in order, of the current transaction in the transaction set.
        :type ts_done: int
        :param ts_total: How much transactions are present in the transaction set.
        :type ts_total: int
        """
        # We don't have any package or action (actually, it's probably that it
        # will be all empty), let's just return earlier.
        if action is None or package is None:
            loggerinst.debug("No action or package was provided in the callback.")
            return

        # We convert the package here to a str because we just stand a
        # normal-standard str comparision rather than what is implemented in
        # `yum.sqlitesack.YumAvailablePackageSqlite`, as this class does
        # version comparision and a bunch of other stuff. We don't care about
        # any of that, we just want to check if the package name is equal or
        # different.
        package = str(package)

        message = "%s: %s [%s/%s]" % (pkgmanager.transaction.ACTIONS.get(action), package, ts_done, ts_total)

        # Prevent the same package being present in the logs.
        if self.last_package_seen != package:
            loggerinst.info(message)

        self.last_package_seen = package
