import os

import pytest

from conftest import SYSTEM_RELEASE_ENV


@pytest.fixture(scope="function")
def one_kernel(shell):
    if os.environ["TMT_REBOOT_COUNT"] == "0":
        # installing kernel package
        assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
        # set default kernel
        if "centos-7" in SYSTEM_RELEASE_ENV:
            assert shell("grub2-set-default 'CentOS Linux (3.10.0-1160.el7.x86_64) 7 (Core)'").returncode == 0
        elif "oracle-7" in SYSTEM_RELEASE_ENV:
            assert (
                shell("grub2-set-default 'Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64'").returncode == 0
            )

        # replace url in yum.repos.d rhel repo
        original_url = (
            r"baseurl = http://rhsm-pulp.corp.redhat.com/content/dist/rhel/server/7/$releasever/$basearch/os/"
        )
        new_url = "baseurl=http://rhsm-pulp.corp.redhat.com/content/dist/rhel/server/7/7.9/x86_64/os/"
        shell('sed -i "s+{}+{}+g" /etc/yum.repos.d/rhel7.repo'.format(original_url, new_url))
        shell("tmt-reboot -t 600")

    if os.environ["TMT_REBOOT_COUNT"] == "1":
        try:
            # remove all kernels except the kernel-3.10.0-1160.el7.x86_64
            shell("rpm -qa kernel | grep -v 'kernel-3.10.0-1160.el7.x86_64' | xargs yum -y remove")
            assert shell("rpm -qa kernel | wc -l").output == "1\n"

            # Also remove the UEK on Oracle
            if "oracle" in SYSTEM_RELEASE_ENV:
                assert shell("yum remove -y kernel-uek")
        except AssertionError as e:
            print(f"An AssertionError was raised: \n{e}")
            shell("tmt-report-result /tests/integration/tier1/destructive/one-kernel-scenario/one_kernel_scenario FAIL")
            raise

        shell("tmt-reboot -t 600")


def test_one_kernel_scenario(shell, convert2rhel, one_kernel):
    """TODO(r0x0d) better description and function name"""

    if os.environ["TMT_REBOOT_COUNT"] == "2":

        # The nfnetlink kmod is causing issues on OracleLinux 7
        if "oracle-7" in SYSTEM_RELEASE_ENV:
            shell("rmmod nfnetlink")

        enable_repo_opt = """
            --enablerepo rhel-7-server-rpms
            --enablerepo rhel-7-server-optional-rpms
            --enablerepo rhel-7-server-extras-rpms
            """

        # python3 causes issues
        assert shell("yum remove -y python3").returncode == 0

        # The 'updates' and 'ol7_latest' repository on 'CentOS7' and 'Oracle7' respectively
        # contains higher version of kernel, so the update would get inhibited due to
        # the kernel not being at the latest version installed on the system.
        # We also need to enable env variable to allow unsupported rollback.
        if "centos" in SYSTEM_RELEASE_ENV:
            assert shell("yum-config-manager --disable updates").returncode == 0
        elif "oracle" in SYSTEM_RELEASE_ENV:
            assert shell("yum-config-manager --disable ol7_latest").returncode == 0
            # This internal repo breaks the conversion on the instances we are getting
            # from Testing Farm
            shell("rm /etc/yum.repos.d/copr_build-convert2rhel-1.repo")

        with convert2rhel("-y --no-rhsm {} --debug".format(enable_repo_opt)) as c2r:
            c2r.expect("Conversion successful!")

        assert c2r.exitstatus == 0

        # replace url in yum.repos.d rhel repo to the original one
        original_url = (
            r"baseurl = https://rhsm-pulp.corp.redhat.com/content/dist/rhel/server/7/\$releasever/\$basearch/os/"
        )
        new_url = "baseurl=https://rhsm-pulp.corp.redhat.com/content/dist/rhel/server/7/7.9/x86_64/os/"
        shell('sed -i "s+{}+{}+g" /etc/yum.repos.d/rhel7.repo'.format(new_url, original_url))

        enable_repo_opt = (
            "--enable rhel-7-server-rpms --enable rhel-7-server-optional-rpms --enable rhel-7-server-extras-rpms"
        )
        shell("yum-config-manager {}".format(enable_repo_opt))

        assert shell("yum install -y python3 --enablerepo=*").returncode == 0
