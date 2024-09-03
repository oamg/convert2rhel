from conftest import TEST_VARS


def test_sub_man_rollback(convert2rhel, shell, required_packages):
    """
    Verify that convert2rhel removes and backs up the original vendor subscription-manager packages, including
    python3-syspurpose and python3-cloud-what which are also built out of the subscription-manager SRPM.

    Not removing and backing up the python3-syspurpose and python3-cloud-what packages on CentOS Linux 8.5 was causing
    a rollback failure when an older version of these two packages was installed.

    When a reinstallation of removed packages failed during the rollback due to not having the right versions of updated
    dependencies backed up, the system was left without the centos-linux-release package installed, leading to the
    $releasever variable being undefined, and ultimately causing a traceback during a subsequent execution of
    convert2rhel (https://issues.redhat.com/browse/RHELC-762).
    """
    # By running convert2rhel twice we make sure that the rollback of the first run
    # correctly reinstalled centos-linux-release and subscription-manager* and the second run then does not fail
    # due to not being able to expand the $releasever variable
    for run in range(2):
        with convert2rhel(
            "-y --serverurl {} --username {} --password {} --debug".format(
                TEST_VARS["RHSM_SERVER_URL"],
                TEST_VARS["RHSM_SCA_USERNAME"],
                TEST_VARS["RHSM_SCA_PASSWORD"],
            )
        ) as c2r:
            assert c2r.expect("Validate the dnf transaction") == 0
            # At this point the centos-linux-release package is already installed
            c2r.sendcontrol("c")
            # Expect rollback, otherwise TIMEOUT
            c2r.expect("WARNING - Abnormal exit! Performing rollback", timeout=10)

        assert c2r.exitstatus == 1
