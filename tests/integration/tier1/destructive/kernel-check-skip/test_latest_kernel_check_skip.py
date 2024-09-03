import os
import re

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS


def test_latest_kernel_check_skip(shell, convert2rhel, backup_directory):
    """
    Verify that it's possible to run the full conversion with older kernel,
    than available in the RHEL repositories.
        1/ Install older kernel on the system
        2/ Make sure the `CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK` is in place
            * doing that we also verify, the deprecated envar is still allowed
        3/ Enable *just* the rhel-7-server-rpms repository prior to conversion
        4/ Run conversion verifying the conversion is not inhibited and completes successfully
    """
    eus_backup_dir = os.path.join(backup_directory, "eus")
    repodir = "/etc/yum.repos.d/"

    # Move all the repos away except the rhel7.repo
    for file in os.listdir(repodir):
        old_filepath = os.path.join(repodir, file)
        new_filepath = os.path.join(backup_directory, file)
        if file != "rhel7.repo":
            os.rename(old_filepath, new_filepath)

    # EUS version use hardcoded repos from c2r as well
    if re.match(r"^(alma|rocky)-8\.8$", SYSTEM_RELEASE_ENV) or "centos-8-latest" in SYSTEM_RELEASE_ENV:
        assert shell(f"mkdir {eus_backup_dir}").returncode == 0
        assert shell(f"mv /usr/share/convert2rhel/repos/* {eus_backup_dir}").returncode == 0

    # Resolve the $releasever for CentOS 7 latest manually as it gets resolved to `7` instead of required `7Server`
    if SYSTEM_RELEASE_ENV in ["centos-7", "oracle-7"]:
        shell(r"sed -i 's/\$releasever/7Server/g' /etc/yum.repos.d/rhel7.repo")

    # Disable all repositories
    shell("yum-config-manager --disable *")
    # Enable just the rhel-7-server-rpms repo
    shell("yum-config-manager --enable rhel-7-server-rpms --releasever 7Server")

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
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
