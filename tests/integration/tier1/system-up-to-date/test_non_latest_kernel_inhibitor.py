import platform

from envparse import env


def set_latest_kernel(shell):
    # We need to get the name of the latest kernel
    # present in the repositories

    # Install 'yum-utils' required by the repoquery command
    shell("yum install yum-utils -y")

    # Get the name of the latest kernel
    latest_kernel = shell(
        "repoquery --quiet --qf '%{BUILDTIME}\t%{VERSION}-%{RELEASE}' kernel 2>/dev/null | tail -n 1 | awk '{printf $NF}'"
    ).output

    # Get the full name of the kerenl
    full_name = shell(
        "grubby --info ALL | grep \"title=.*{}\" | tr -d '\"' | sed 's/title=//'".format(latest_kernel)
    ).output

    # Set the latest kernel as the one we want to reboot to
    shell("grub2-set-default '{}'".format(full_name.strip()))


def test_non_latest_kernel(shell, convert2rhel):
    """
    System has non latest kernel installed, thus the conversion
    has to be inhibited.
    """

    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        if "centos-7" in platform.platform() or "oracle-7" in platform.platform():
            c2r.expect(
                "The version of the loaded kernel is different from the latest version on the enabled system repositories."
            )
        else:
            c2r.expect(
                "The version of the loaded kernel is different from the latest version on repositories defined in the"
            )
    assert c2r.exitstatus != 0

    # Clean up, reboot is required after setting the newest kernel
    set_latest_kernel(shell)
