import os
import platform


def test_run_conversion_using_custom_repos(shell, convert2rhel):
    "TODO better description and function name"

    system_distro = platform.platform()

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
    if "centos" in system_distro:
        assert shell("yum-config-manager --disable updates").returncode == 0
    elif "oracle" in system_distro:
        assert shell("yum-config-manager --disable ol7_latest").returncode == 0
        # This internal repo breaks the conversion on the instances we are getting
        # from Testing Farm
        shell("rm /etc/yum.repos.d/copr_build-convert2rhel-1.repo")

    os.environ["CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK"] = "1"
    os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"] = "1"

    with convert2rhel("-y --no-rpm-va --disable-submgr {} --debug".format(enable_repo_opt)) as c2r:
        c2r.expect("Conversion successful!")

    assert c2r.exitstatus == 0

    assert shell("yum install -y python3 --enablerepo=*").returncode == 0
