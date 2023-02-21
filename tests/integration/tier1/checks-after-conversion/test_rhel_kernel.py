import pytest


@pytest.mark.rhel_kernel
def test_one_kernel_scenario(shell):
    # Check if kernel is RHEL one
    kernel = shell("rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE} %{VENDOR}\n' kernel").output
    assert "Red Hat" in kernel
    # TODO This may return more than 1 kernel -> maybe it's better to check that every kernel is RHEL one (eg. do some for each..)
