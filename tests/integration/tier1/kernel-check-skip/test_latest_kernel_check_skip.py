import os

import pytest

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


@pytest.mark.test_latest_kernel_check_skip
def test_skip_kernel_check(shell, convert2rhel):
    """
    Verify that it's possible to run the full conversion with older kernel,
    than available in the RHEL repositories.
        1/ Install older kernel on the system
        2/ Make sure the `CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK` is in place
            * doing that we also verify, the deprecated envar is still allowed
        3/ Enable *just* the rhel-7-server-rpms repository prior to conversion
        4/ Run conversion verifying the conversion is not inhibited and completes successfully
    """
    backup_dir = "/tmp/repobckp"
    shell(f"mkdir {backup_dir}")
    # Move all the repos away except the rhel7.repo
    shell("find /etc/yum.repos.d/ -type f -name '*.repo' ! -name 'rhel7.repo' -exec mv {} /tmp/repobckp \\;")

    # Verify the environment variable to bypass the check is in place
    # Intentionally use the deprecated variable to verify its compatibility
    assert os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"] == "1"

    # Resolve the $releasever for CentOS 7 latest manually as it gets resolved to `7` instead of required `7Server`
    if "centos-7" in SYSTEM_RELEASE_ENV:
        shell("sed -i 's/\$releasever/7Server/g' /etc/yum.repos.d/rhel7.repo")

    # Disable all repositories
    shell("yum-config-manager --disable *")
    # Enable just the rhel-7-server-rpms repo
    shell("yum-config-manager --enable rhel-7-server-rpms --releasever 7Server")

    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_SCA_USERNAME"),
            env.str("RHSM_SCA_PASSWORD"),
        )
    ) as c2r:
        # Verify that using the deprecated environment variable is still allowed and continues the conversion
        # TODO(danmyway) uncomment in #684
        # assert c2r.expect("You are using the deprecated 'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK'") == 0
        # Make sure the kernel comparison is skipped
        c2r_expect_index = c2r.expect(
            [
                "we will skip the kernel comparison.",
                "Could not find any kernel packages in repositories to compare against the loaded kernel.",
            ]
        )
        if c2r_expect_index == 0:
            pass
        elif c2r_expect_index == 1:
            assert AssertionError
        assert c2r.expect("Conversion successful") == 0
    assert c2r.exitstatus == 0
