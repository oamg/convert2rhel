def test_one_kernel_scenario(shell):
    os_release = shell("cat /etc/os-release").output
    assert "Red Hat Enterprise Linux" in os_release

    # Check if kernel is RHEL one
    kernel = shell("rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE} %{VENDOR}\n' kernel").output
    assert "Red Hat" in kernel
