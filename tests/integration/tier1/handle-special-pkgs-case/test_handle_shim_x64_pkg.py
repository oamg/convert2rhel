from envparse import env


# TODO(r0x0d): Remove this integration test as it probably is not needed anymore.
def test_handle_shim_x64_pkg(shell, convert2rhel):
    """Ensure c2r handle the shim-x64 package.

    This test needs to pass on both BIOS and UEFI systems as this packages needs
    to have it's protection config removed during the conversion.
    """

    shim_x64_pkg = "shim-x64"
    # Install the shim-x64 package
    assert (
        shell(
            f"yum install -y {shim_x64_pkg}",
        ).returncode
        == 0
    )

    # run utility until the reboot
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0

    # Check that the package is still present on the system
    assert shell(f"rpm -qi {shim_x64_pkg}").returncode != 0
