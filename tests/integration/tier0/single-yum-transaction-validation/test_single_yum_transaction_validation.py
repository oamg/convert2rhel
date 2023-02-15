import os
import shutil

import pytest

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


PKI_ENTITLEMENT_CERTS_PATH = "/etc/pki/entitlement"


def backup_entitlement_certs():
    """
    Utillity function to backup and remove the entitlment cert as soon as we
    notice then in the the `PKI_ENTITLEMENT_CERTS_PATH`.
    """
    original_certs = os.listdir(PKI_ENTITLEMENT_CERTS_PATH)

    for cert in original_certs:
        full_cert = "{}/{}".format(PKI_ENTITLEMENT_CERTS_PATH, cert)
        new_cert = "{}.bk".format(full_cert)
        shutil.move(full_cert, new_cert)


@pytest.mark.package_download_error
def test_package_download_error(convert2rhel):
    """
    Remove the entitlement certs found at /etc/pki/entitlement during package
    download phase for both yum and dnf transactions.

    This will run the conversion up to the point where we valiate the
    transaction, when it reaches a specific point of the validation, we remove
    the entitlement certs found in /etc/pki/entitlement/*.pem to ensure that the
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

    if "oracle" in SYSTEM_RELEASE_ENV:
        server_sub = "Oracle Linux Server"

    if "8" in SYSTEM_RELEASE_ENV:
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
        backup_entitlement_certs()
        assert c2r.expect_exact(final_message, timeout=600) == 0

    assert c2r.exitstatus == 1


@pytest.mark.transaction_validation_error
def test_transaction_validation_error(convert2rhel):
    """
    Remove the entitlement certs found at /etc/pki/entitlement during transaction
    processing to throw the following yum error: pkgmanager.Errors.YumDownloadError

    This will run the conversion up to the point where we valiate the
    transaction, when it reaches a specific point of the validation, we remove
    the entitlement certs found in /etc/pki/entitlement/*.pem to ensure that the
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
        backup_entitlement_certs()
        assert c2r.expect_exact("Failed to validate the yum transaction.", timeout=600) == 0

    assert c2r.exitstatus == 1
