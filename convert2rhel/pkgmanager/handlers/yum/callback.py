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
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
# Copyright 2005 Duke University
# Parts Copyright 2007 Red Hat, Inc
#
#   License above taken from the original code at:
#
#       https://github.com/rpm-software-management/yum/blob/master/yum/rpmtrans.py
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
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
#   License above taken from the original code at:
#
#       https://github.com/rpm-software-management/yum/blob/master/yum/callbacks.py
#
import logging

from convert2rhel import pkgmanager


loggerinst = logging.getLogger(__name__)
"""Instance of the logger used in this module."""

# We need to double inherit here, both from the callback class and the base
# object class, just to initialize properly with `super`
class PackageDownloadCallback(pkgmanager.DownloadProgress, object):
    """Package download callback for YUM transaction."""

    def __init__(self):
        """Constructor for the package download progress indicator.

        We initialize a few properties here for keeping track of progression of
        the downloaded files.
        """
        super(PackageDownloadCallback, self).__init__()
        # Same strategy as used in yum.rpmtrans.SimpleCliCallBack. We
        # hold the last package name to not print it twice, avoiding
        # spamming msgs.
        self.last_package_seen = None

    def updateProgress(self, name, frac, fread, ftime):
        """Update and output the message that we sent to the user.

        This method, in the `DownloadBaseCallback` class, is meant to be used
        with a progress-bar to show a nice progression for the user, but we are
        using it only to output a simple message to keep track of the packages
        were downloaded, no need to do any fancy progress-bar.

        :param name: File that is being downloaded in the transaction.
        :type name: str
        :param frac: A number between `0` and `1` that represents the file that is being downloaded or not.
        :type frac: int
        :param fread: String containing how much bytes was read in the download.
        :type fread: str
        :param ftime: String that contains the remaining time for te package to be finish the download.
        :type ftime: str
        """
        # The base API will call this callback class on every package update,
        # not matter if it is the same update or not, so, the below statement
        # prevents the same message being sent more than once to the user.
        if self.last_package_seen != name:
            # Metadata download abut repositories will be sent to this class too.
            if name.endswith(".rpm"):
                loggerinst.info("Downloading package: %s", name)
            else:
                loggerinst.debug("Downloading repository metadata: %s", name)

        self.last_package_seen = name


class TransactionDisplayCallback(pkgmanager.TransactionDisplay, object):
    """Transaction display callback for YUM transaction."""

    def __init__(self):
        """Constructor that overrides initialization for SimpleCliCallBack()."""
        super(TransactionDisplayCallback, self).__init__()
        # Hold the last package name to not print it twice, avoiding
        # spamming msgs.
        self.last_package_seen = None

    def event(self, package, action, te_current, te_total, ts_current, ts_total):
        """Process and output the RPM operations in the transaction.

        .. note::
            Yum API send the `package` paramter as two different types :holding-back-tears:.
            If the package comes as a `str`, then it's a cleanup, if it's a
            `yum.sqlitesack.YumAvailablePackageSqlite`, then it's a normal
            package being processed.

        :param package: Package being processed in the transaction.
        :type param: str | yum.sqlitesack.YumAvailablePackageSqlite
        :param action: The type of the action being used for the current
            `package`. Only values that came from `rpmtrans.RPMBaseCallback.action` are valid.
        :type action: int
        :param te_current: How much work was already been done in the transaction.
        :type te_current: int
        :param te_total: How much work in total is present in the transaction.
        :type te_total: int
        :param ts_current: Number, in order, of the current transaction in the transaction set.
        :type ts_current: int
        :param ts_total: How much transactions are present in the transaction set.
        :type ts_total: int
        """
        message = "%s: %s [%s/%s]"

        # We convert the package here to a str because we just stand a
        # normal-standard str comparision rather than what is implemented in
        # `yum.sqlitesack.YumAvailablePackageSqlite`, as this class does
        # version comparision and a bunch of other stuff. We don't care about
        # any of that, we just want to check if the package name is equal or
        # different.
        package = str(package)

        message = message % (self.action[action], package, ts_current, ts_total)

        # The base API will call this callback class on every package update,
        # not matter if it is the same update or not, so, the below statement
        # prevents the same message being sent more than once to the user.
        if self.last_package_seen != package:
            loggerinst.info(message)

        self.last_package_seen = package
