from conftest import TEST_VARS


def test_yum_distro_sync(convert2rhel, shell):
    """Test yum distro-sync command edge-cases when given packages aren't in enabled repositories.

    Following is done:
        1) Install a problematic package (cpaste) - done in preparation step
        2) Run the conversion
        3) Run the distro-sync in two variants
            - just with the problematic package
            - with some another package, which is in RHEL repositories
        4) Do the same checks and conditions as is in convert2rhel/pkghandler.py in call_yum_cmd_w_downgrades.

    Another problem is, that yum behaves differently on Centos 7 and Centos 8
        - on CentOS Linux 7 returns 0 and any error in both cases
        - on CentOS Linux 8 returns 0 and any error if in list of packages for distro-sync is at least
          one, which can be successfully distro synced. If all the given cannot be synced, there
          is an error, which caused problems: https://issues.redhat.com/browse/RHELC-150. But
          the error isn't in fact error, the package stays there
          and just isn't supported by Red Hat.
    """

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0

    # any error on Centos 7 and Centos 8
    out = shell("yum distro-sync cpaste zip")
    assert condition_test(out.output, out.returncode)
    # an error on Centos 8, which should be skipped
    out = shell("yum distro-sync cpaste")
    assert condition_test(out.output, out.returncode)


def condition_test(output, ret_code):
    """
    Verifies __THE SAME__ conditions as in convert2rhel/pkghandler.py.
    Just small change -
    they return True or False depending on success or not.
    """

    if ret_code == 0:
        return True

    # handle success condition #2
    # false positive: yum returns non-zero code when there is nothing to do
    nothing_to_do_error_exists = output.endswith("Error: Nothing to do\n")
    if ret_code == 1 and nothing_to_do_error_exists:
        return True

    # handle success condition #3
    # false positive: yum distro-sync returns non-zero code when got package, which isn't in rhel repos
    # on older (original yum) returns 0, but on newer dnf 1
    # just in case if all packages given aren't in rhel repos. If one of them is, ret code is 0 and finishes successfully
    no_packages_marked_error_exists = output.endswith("Error: No packages marked for distribution synchronization.\n")
    if ret_code == 1 and no_packages_marked_error_exists:
        return True

    return False
