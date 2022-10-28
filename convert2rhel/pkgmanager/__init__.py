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

try:
    from yum import *

    # This is added here to prevent a generic try-except in the
    # `check_package_updates()` function.
    from yum.Errors import RepoError  # lgtm[py/unused-import]

    TYPE = "yum"
except ImportError as e:
    from dnf import *  # pylint: disable=import-error

    # This is added here to prevent a generic try-except in the
    # `check_package_updates()` function.
    from dnf.exceptions import RepoError  # lgtm[py/unused-import]

    TYPE = "dnf"


def create_transaction_handler():
    """Create a new instance of TransactionHandler class.

    This function will return a new instance of the TransactionHandler abstract
    class, that will be either the YumTransactionHandler or
    DnfTransactionHandler dependening on the running system.

    :return: An instance of the TransactionHandler abstract class.
    :rtype: TransactionHandler
    """
    # This is here to prevent a recursive import on both handler classes. We
    # are doing this in this ugly way to avoid a massive refactor for the merge
    # yum transaction work, specially because this module has lots of other
    # modules that depend on this.
    # The wisest thing would be to wait on the RHELC-160 work to be started,
    # and then, refactor this function to have only one entrypoint, hence:
    # TODO(r0x0d): Refactor this as part of RHELC-160.
    if TYPE == "yum":
        from convert2rhel.pkgmanager.handlers.yum import YumTransactionHandler

        return YumTransactionHandler()
    elif TYPE == "dnf":
        from convert2rhel.pkgmanager.handlers.dnf import DnfTransactionHandler

        return DnfTransactionHandler()
