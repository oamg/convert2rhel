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

from convert2rhel import utils


loggerinst = logging.getLogger(__name__)

try:
    from yum import *
    from yum.callbacks import DownloadBaseCallback as DownloadProgress

    # This is added here to prevent a generic try-except in the
    # `check_package_updates()` function.
    from yum.Errors import RepoError
    from yum.rpmtrans import SimpleCliCallBack as TransactionDisplay

    TYPE = "yum"
except ImportError as e:
    from dnf import *
    from dnf.callback import Depsolve, DownloadProgress

    # This is added here to prevent a generic try-except in the
    # `check_package_updates()` function.
    from dnf.exceptions import RepoError
    from dnf.yum.rpmtrans import TransactionDisplay

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


def clean_yum_metadata():
    """Remove cached metadata from yum.

    This is to make sure that Convert2RHEL works with up-to-date data from repositories before, for instance, querying
    whether the system has the latest package versions installed, or before checking whether enabled repositories have
    accessible URLs.
    """
    # We are using run_subprocess here as an alternative to call_yum_cmd
    # which doesn't apply the correct --enablerepos option because if we call this
    # earlier in the conversion the tool doesn't initialize the necessary functions in SystemInfo.
    # The viable solution was calling the yum command as a subprocess manually
    # instead of using that function wrapper.
    output, ret_code = utils.run_subprocess(
        ("yum", "clean", "metadata", "--enablerepo=*", "--quiet"), print_output=False
    )
    loggerinst.debug("Output of yum clean metadata:\n%s" % output)

    if ret_code != 0:
        loggerinst.warning("Failed to clean yum metadata:\n%s" % output)
        return

    loggerinst.info("Cached repositories metadata cleaned successfully.")
