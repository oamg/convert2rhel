import os.path

import pytest

from envparse import env


@pytest.fixture(scope="function")
def convert2rhel_repo(shell):
    assert shell("rpm -qi subscription-manager").returncode == 0
    # The following repository requires the redhat-uep.pem certificate. convert2rhel will try accessing the repo and
    # by running convert2rhel twice makes sure that the rollback of the first run correctly reinstalled the certificate
    # when installing subscription-manager-rhsm-certificates.
    c2r_repo = "/etc/yum.repos.d/convert2rhel.repo"

    assert shell(f"curl -o {c2r_repo} https://ftp.redhat.com/redhat/convert2rhel/8/convert2rhel.repo").returncode == 0
    assert os.path.exists(c2r_repo) is True

    yield

    assert shell(f"rm -f {c2r_repo}")
    assert os.path.exists(c2r_repo) is False


@pytest.mark.test_sub_man_rollback
def test_sub_man_rollback(convert2rhel, shell, required_packages, convert2rhel_repo):
    """
    Verify that convert2rhel removes and backs up the original vendor subscription-manager packages, including
    python3-syspurpose and python3-cloud-what which are also built out of the subscription-manager SRPM.

    Not removing and backing up the python3-syspurpose and python3-cloud-what packages on CentOS Linux 8.5 was causing
    a rollback failure when an older version of these two packages was installed.

    The rollback failure caused the following issues during the subsequent second run of convert2rhel:
    1. when the rollback happened before removing the centos-linux-release package, the removed
      subscription-manager-rhsm-certificates was not re-installed back during the rollback leading to a missing
      /etc/rhsm/ca/redhat-uep.pem file which is necessary for accessing the official convert2rhel repo on CDN
      (https://issues.redhat.com/browse/RHELC-744)
    2. when the rollback happened before removing the centos-linux-release package, this package was not re-installed
      back during the rollback and that lead to the $releasever variable being undefined, ultimately causing a traceback
      when using the DNF python API (https://issues.redhat.com/browse/RHELC-762)
    """

    for run in range(2):
        with convert2rhel(
            "-y --no-rpm-va --serverurl {} --username {} --password {} --debug".format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
            )
        ) as c2r:
            assert c2r.expect("Validate the dnf transaction") == 0
            # At this point the centos-linux-release package is already installed
            c2r.sendcontrol("c")
