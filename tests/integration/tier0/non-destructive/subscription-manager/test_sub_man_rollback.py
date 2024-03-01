import os.path

import pytest

from conftest import TEST_VARS


@pytest.mark.test_sub_man_rollback
def test_sub_man_rollback(convert2rhel, shell, required_packages):
    """
    Verify that convert2rhel removes and backs up the original vendor subscription-manager packages, including
    python3-syspurpose and python3-cloud-what which are also built out of the subscription-manager SRPM.

    Not removing and backing up the python3-syspurpose and python3-cloud-what packages on CentOS Linux 8.5 was causing
    a rollback failure when an older version of these two packages was installed.

    The rollback failure caused the following issue during the subsequent second run of convert2rhel:
      When the rollback happened before removing the centos-linux-release package, this package was not re-installed
      back during the rollback and that lead to the $releasever variable being undefined, ultimately causing a traceback
      when using the DNF python API (https://issues.redhat.com/browse/RHELC-762)
    """
    # By running convert2rhel twice we make sure that the rollback of the first run
    # correctly reinstalled centos-linux-release and subscription-manager* and the second run then does not fail
    # due to not being able to expand the $releasever variable
    for run in range(2):
        with convert2rhel(
            "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
                TEST_VARS["RHSM_SERVER_URL"],
                TEST_VARS["RHSM_USERNAME"],
                TEST_VARS["RHSM_PASSWORD"],
                TEST_VARS["RHSM_POOL"],
            )
        ) as c2r:
            assert c2r.expect("Validate the dnf transaction") == 0
            # At this point the centos-linux-release package is already installed
            c2r.sendcontrol("c")
            # Expect rollback, otherwise TIMEOUT
            c2r.expect("WARNING - Abnormal exit! Performing rollback", timeout=10)

        assert c2r.exitstatus == 1
