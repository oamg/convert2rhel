import os

import pytest

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


PKI_ENTITLEMENT_CERTS_PATH = "/etc/pki/entitlement"

SERVER_SUB = "CentOS Linux"
PKGMANAGER = "yum"
FINAL_MESSAGE = "There are no suitable mirrors available for the loaded repositories."

if "oracle" in SYSTEM_RELEASE_ENV:
    SERVER_SUB = "Oracle Linux Server"

if "8" in SYSTEM_RELEASE_ENV:
    PKGMANAGER = "dnf"
    FINAL_MESSAGE = "Failed to download the transaction packages."


@pytest.fixture()
def yum_cache(shell):
    """
    We need to clean yum cache of packages and metadata downloaded by the previous test runs
    to correctly reproduce the transaction validation download fail.
    """
    assert shell("yum clean all --enablerepo=* --quiet").returncode == 0
    assert shell(f"rm -rf /var/cache/{PKGMANAGER}")


def remove_entitlement_certs():
    """
    Utility function to remove the entitlement certificate as soon as we
    notice it in the `PKI_ENTITLEMENT_CERTS_PATH`.

    We don't need to back it up and then restore it because the PKI_ENTITLEMENT_CERTS_PATH folder is only created during
    the conversion when the subscription-manager package is installed. And the .pem certificate is being generated by
    subscription-manager in the folder during the system registration. So to have the test system clean after the test
    finishes the certs shouldn't be present.
    """
    for cert_filename in os.listdir(PKI_ENTITLEMENT_CERTS_PATH):
        cert_path = os.path.join(PKI_ENTITLEMENT_CERTS_PATH, cert_filename)
        try:
            os.unlink(cert_path)
        except Exception as e:
            print("Failed to delete %s. Reason: %s" % (cert_path, e))


@pytest.mark.test_package_download_error
def test_package_download_error(convert2rhel, shell, yum_cache):
    """
    Remove the entitlement certs found at /etc/pki/entitlement during package
    download phase for both yum and dnf transactions.

    This will run the conversion up to the point where we validate the transaction.
    When the validation reaches a specific point, we remove the entitlement certs
    found in /etc/pki/entitlement/*.pem to ensure that the
    tool is doing a proper rollback when there is any failure during the package
    download.

    The package download happens in different phases for yum and dnf, yum
    downloads the packages during the `processTransaction` method call, while dnf
    has a specific method that processes and downloads the packages in the
    transaction.
    """
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Validate the {} transaction".format(PKGMANAGER))
        c2r.expect("Adding {} packages to the {} transaction set.".format(SERVER_SUB, PKGMANAGER))
        remove_entitlement_certs()
        assert c2r.expect_exact(FINAL_MESSAGE, timeout=600) == 0

    assert c2r.exitstatus == 1


@pytest.mark.test_transaction_validation_error
def test_transaction_validation_error(convert2rhel, shell, yum_cache):
    """
    Remove the entitlement certs found at /etc/pki/entitlement during transaction
    processing to throw the following yum error: pkgmanager.Errors.YumDownloadError

    This will run the conversion up to the point where we validate the transaction.
    When the validation reaches a specific point, we remove the entitlement certs
    found in /etc/pki/entitlement/*.pem to ensure that the
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
        remove_entitlement_certs()
        assert c2r.expect_exact("Failed to validate the yum transaction.", timeout=600) == 0

    assert c2r.exitstatus == 1
