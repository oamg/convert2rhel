__metaclass__ = type

import logging
import os
import shutil
import tempfile

from convert2rhel.exceptions import ImportGPGKeyError
from convert2rhel.utils.term import run_subprocess


loggerinst = logging.getLogger(__name__)


def find_keyid(keyfile):
    """
    Find the keyid as used by rpm from a gpg key file.

    :arg keyfile: The filename that contains the gpg key.

    .. note:: rpm doesn't use the full gpg fingerprint so don't use that even though it would be
        more secure.
    """
    # Newer gpg versions have several easier ways to do this:
    # gpg --with-colons --show-keys keyfile (Can pipe keyfile)
    # gpg --with-colons --import-options show-only --import keyfile  (Can pipe keyfile)
    # gpg --with-colons --import-options import-show --dry-run --import keyfile (Can pipe keyfile)
    # But as long as we need to work on RHEL7 we can't use those.

    # GPG needs a writable diretory to put default config files
    temporary_dir = tempfile.mkdtemp()
    temporary_keyring = os.path.join(temporary_dir, "keyring")

    try:
        # Step 1: Import the key into a temporary keyring (the list-keys command can't operate on
        # a single asciiarmored key)
        output, ret_code = run_subprocess(
            [
                "gpg",
                "--no-default-keyring",
                "--keyring",
                temporary_keyring,
                "--homedir",
                temporary_dir,
                "--import",
                keyfile,
            ],
            print_output=False,
        )
        if ret_code != 0:
            raise ImportGPGKeyError("Failed to import the rpm gpg key into a temporary keyring: %s" % output)

        # Step 2: Print the information about the keys in the temporary keyfile.
        # --with-colons give us guaranteed machine parsable, stable output.
        output, ret_code = run_subprocess(
            [
                "gpg",
                "--no-default-keyring",
                "--keyring",
                temporary_keyring,
                "--homedir",
                temporary_dir,
                "--list-keys",
                "--with-colons",
            ],
            print_output=False,
        )
        if ret_code != 0:
            raise ImportGPGKeyError("Failed to read the temporary keyring with the rpm gpg key: %s" % output)
    finally:
        # Try five times to work around a race condition:
        #
        # Gpg writes a temporary socket file for a gpg-agent into
        # --homedir.  Sometimes gpg removes that socket file after rmtree
        # has determined it should delete that file but before the deletion
        # occurs. This will cause a FileNotFoundError (OSError on Python
        # 2).  If we encounter that, try to run shutil.rmtree again since
        # we should now be able to remove all the files that were left.
        for _dummy in range(0, 5):
            try:
                # Remove the temporary keyring.  We can't use the context manager
                # for this because it isn't available on Python-2.7 (RHEL7)
                shutil.rmtree(temporary_dir)
            except OSError as e:
                # File not found means rmtree tried to remove a file that had
                # already been removed by the time it tried.
                if e.errno != 2:
                    raise
            else:
                break
        else:
            # If we get here, we tried and failed to rmtree five times
            # Don't make this fatal but do let the user know so they can clean
            # it up themselves.
            loggerinst.info(
                "Failed to remove temporary directory %s that held Red Hat gpg public keys." % temporary_dir
            )

    keyid = None
    for line in output.splitlines():
        if line.startswith("pub"):
            fields = line.split(":")
            fingerprint = fields[4]
            # The keyid as represented in rpm's fake packagename is only the last 8 hex digits
            # Example: gpg-pubkey-d651ff2e-5dadbbc1
            keyid = fingerprint[-8:]
            break

    if not keyid:
        raise ImportGPGKeyError("Unable to determine the gpg keyid for the rpm key file: %s" % keyfile)

    return keyid.lower()
