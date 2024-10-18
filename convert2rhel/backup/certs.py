# -*- coding: utf-8 -*-
#
# Copyright(C) 2024 Red Hat, Inc.
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

import errno
import os
import shutil

from convert2rhel import exceptions, utils
from convert2rhel.backup import RestorableChange
from convert2rhel.logger import root_logger
from convert2rhel.utils import files


logger = root_logger.getChild(__name__)


class RestorableRpmKey(RestorableChange):
    """Import a GPG key into rpm in a reversible fashion."""

    def __init__(self, keyfile):
        """
        Setup a RestorableRpmKey to reflect the GPG key in a file.

        :arg keyfile: Filepath for a GPG key.  The RestorableRpmKey instance will be able to import
            this into the rpmdb when enabled and remove it when restored.
        """
        super(RestorableRpmKey, self).__init__()
        self.previously_installed = None
        self.keyfile = keyfile
        self.keyid = utils.find_keyid(keyfile)

    def enable(self):
        """Ensure that the GPG key has been imported into the rpmdb."""
        # For idempotence, do not back this up if we've already done so.
        if self.enabled:
            return

        if not self.installed:
            output, ret_code = utils.run_subprocess(["rpm", "--import", self.keyfile], print_output=False)
            if ret_code != 0:
                raise utils.ImportGPGKeyError("Failed to import the GPG key {}: {}".format(self.keyfile, output))

            self.previously_installed = False

        else:
            self.previously_installed = True

        super(RestorableRpmKey, self).enable()

    @property
    def installed(self):
        """Whether the GPG key has been imported into the rpmdb."""
        output, status = utils.run_subprocess(["rpm", "-q", "gpg-pubkey-{}".format(self.keyid)], print_output=False)

        if status == 0:
            return True

        if status == 1 and "package gpg-pubkey-{} is not installed".format(self.keyid) in output:
            return False

        raise utils.ImportGPGKeyError(
            "Searching the rpmdb for the gpg key {} failed: Code {}: {}".format(self.keyid, status, output)
        )

    def restore(self):
        """Ensure the rpmdb has or does not have the GPG key according to the state before we ran."""
        if self.enabled and self.previously_installed is False:
            utils.run_subprocess(["rpm", "-e", "gpg-pubkey-{}".format(self.keyid)])

        super(RestorableRpmKey, self).restore()


class RestorablePEMCert(RestorableChange):
    """Handling certificates needed for verifying Red Hat services."""

    def __init__(self, source_cert_dir, target_cert_dir):
        super(RestorablePEMCert, self).__init__()

        self._target_cert_dir = target_cert_dir
        self._source_cert_dir = source_cert_dir
        self._cert_filename = _get_cert(source_cert_dir)
        self._source_cert_path = self._get_source_cert_path()
        self._target_cert_path = self._get_target_cert_path()

        self.previously_installed = False

    def _get_source_cert_path(self):
        return os.path.join(self._source_cert_dir, self._cert_filename)

    def _get_target_cert_path(self):
        return os.path.join(self._target_cert_dir, self._cert_filename)

    def enable(self):
        """Install the .pem certificate."""
        if self.enabled:
            return

        if os.path.exists(self._target_cert_path):
            logger.info("Certificate already present at {}. Skipping copy.".format(self._target_cert_path))
            self.previously_installed = True
        else:
            try:
                files.mkdir_p(self._target_cert_dir)
                shutil.copy2(self._source_cert_path, self._target_cert_dir)
            except OSError as err:
                logger.critical_no_exit("OSError({0}): {1}".format(err.errno, err.strerror))
                raise exceptions.CriticalError(
                    id_="FAILED_TO_INSTALL_CERTIFICATE",
                    title="Failed to install certificate.",
                    description="convert2rhel was unable to install a required certificate. This certificate allows the pre-conversion analysis to verify that packages are legitimate RHEL packages.",
                    diagnosis="Failed to install certificate {} to {}. Errno: {}, Error: {}".format(
                        self._get_source_cert_path, self._target_cert_dir, err.errno, err.strerror
                    ),
                )

            logger.info("Certificate {} copied to {}.".format(self._cert_filename, self._target_cert_dir))

        super(RestorablePEMCert, self).enable()

    def restore(self):
        """Remove certificate (.pem), which was copied to system's cert dir."""
        logger.task("Remove installed certificate")

        if self.enabled and not self.previously_installed:
            self._restore()
        else:
            logger.info("Certificate {} was present before conversion. Skipping removal.".format(self._cert_filename))

        super(RestorablePEMCert, self).restore()

    def _restore(self):
        """The actual code to remove the certificate.  Done in a helper method so we can handle all
        the cases where we do not want to remove and still run the base class's restore().

            .. warning::
                Exceptions are not handled and left for handling by the calling code.

        :raises OSError: Can be raised when the file is not found.
        """
        # Check whether any package owns the certificate file.  It is
        # possible that a new rpm package was installed after we copied the
        # certificate into place which owns the certificate.  If that is
        # the case, then we don't want to remove it now.
        output, code = utils.run_subprocess(["rpm", "-qf", self._target_cert_path], print_output=False)

        # * If a file is owned by a package, rpm returns exit code 0 and prints
        #   the package name to stdout.
        # * If the file is not owned by a package, rpm returns exit code 1 and
        #   prints a message about not being owned by any installed package to stdout.
        # * If rpm encounters an error looking for the file (for instance, it
        #   doesn't exist on the filesystem), then it returns exit code 1 and
        #   prints the error message to stderr.
        file_unowned = False
        if code != 0:
            if "not owned by any package" in output:
                file_unowned = True
            elif "No such file or directory" in output:
                logger.info("Certificate already removed from {}".format(self._target_cert_path))
            else:
                logger.warning(
                    "Unable to determine if a package owns certificate {}. Skipping removal.".format(
                        self._target_cert_path
                    )
                )
        else:
            logger.info(
                "A package was installed that owns the certificate {}. Skipping removal.".format(self._target_cert_path)
            )

        # Not safe to remove the certificate because the file might be owned by
        # an rpm package.
        if not file_unowned:
            return

        try:
            os.remove(self._target_cert_path)
            logger.info("Certificate {} removed".format(self._target_cert_path))
        except OSError as err:
            if err.errno == errno.ENOENT:
                # Resolves RHSM error when removing certs, as the system might not have installed any certs yet
                logger.info("No certificates found to be removed.")
                return

            # Will be handled in BackupController
            raise


def _get_cert(cert_dir):
    """Return the .pem certificate filename."""
    if not os.access(cert_dir, os.R_OK | os.X_OK):
        logger.critical("Error: Could not access {}.".format(cert_dir))
    pem_filename = None
    for filename in os.listdir(cert_dir):
        if filename.endswith(".pem"):
            pem_filename = filename
            break
    if not pem_filename:
        logger.critical("Error: No certificate (.pem) found in {}.".format(cert_dir))
    return pem_filename
