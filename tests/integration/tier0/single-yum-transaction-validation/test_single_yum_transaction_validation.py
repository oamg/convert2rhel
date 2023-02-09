import os
import shutil

import pytest

from conftest import SYSTEM_RELEASE
from envparse import env


PKI_ENTITLEMENT_KEYS_PATH = "/etc/pki/entitlement"


def backup_entitlement_keys():
    """
    Utillity function to backup and remove the entitlment key as soon as we
    notice then in the the `PKI_ENTITLEMENT_KEYS_PATH`.
    """
    original_keys = os.listdir(PKI_ENTITLEMENT_KEYS_PATH)

    for key in original_keys:
        full_key = "{}/{}".format(PKI_ENTITLEMENT_KEYS_PATH, key)
        new_key = "{}.bk".format(full_key)
        shutil.move(full_key, new_key)


def rollback_entitlement_keys():
    """Utillity function to rollback entitlment keys and clean-up after the test."""
    backup_keys = os.listdir(PKI_ENTITLEMENT_KEYS_PATH)

    for key in backup_keys:
        # This is already in the format with a .bk at the end of it
        backup_key = "{}/{}".format(PKI_ENTITLEMENT_KEYS_PATH, key)
        original_key = "{}".format(backup_key)
        shutil.move(backup_key, original_key)


@pytest.mark.package_download_error
def test_package_download_error(convert2rhel):
    """
    Remove the entitlement keys found at /etc/pki/entitlement during package
    download phase for both yum and dnf transactions.

    This will run the conversion up to the point where we valiate the
    transaction, when it reaches a specific point of the validation, we remove
    the entitlement keys found in /etc/pki/entitlement/*.pem to ensure that the
    tool is doing a proper rollback when there is any failure during the package
    download.

    The package download happens in different phases for yum and dnf, yum
    download the packages during the `processTransaction` method call, while dnf
    has a specific method that process and download the packages in the
    transaction.
    """

    server_sub = "CentOS Linux"
    pkgmanager = "yum"
    final_message = "There are no suitable mirrors available for the loaded repositories."

    if "oracle" in SYSTEM_RELEASE:
        server_sub = "Oracle Linux Server"

    if "8" in SYSTEM_RELEASE:
        pkgmanager = "dnf"
        final_message = "Failed to download the transaction packages."

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Adding {} packages to the {} transaction set.".format(server_sub, pkgmanager))
        backup_entitlement_keys()
        assert c2r.expect_exact(final_message, timeout=600) == 0

    assert c2r.exitstatus == 1

    rollback_entitlement_keys()


@pytest.mark.transaction_validation_error
def test_transaction_validation_error(convert2rhel):
    """
    Remove the entitlement keys found at /etc/pki/entitlement during transaction
    processing to throw the following yum error: pkgmanager.Errors.YumDownloadError

    This will run the conversion up to the point where we valiate the
    transaction, when it reaches a specific point of the validation, we remove
    the entitlement keys found in /etc/pki/entitlement/*.pem to ensure that the
    tool is doing a proper rollback when the transaction is being processed.
    """
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect(
            "Downloading and validating the yum transaction set, no modifications to the system will happen this time."
        )
        backup_entitlement_keys()
        assert c2r.expect_exact("Failed to validate the yum transaction.", timeout=600) == 0

    assert c2r.exitstatus == 1

    rollback_entitlement_keys()
