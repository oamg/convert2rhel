def test_rhel_kernel(shell):
    """
    After conversion check.
    Verify that every installed kernel is Red Hat kernel.
    """
    installed_kernels = shell("rpm -q --qf '%{NAME} %{VERSION}-%{RELEASE} %{VENDOR}\\n' kernel").output.split("\n")
    # Iterate over the list of installed_kernels and verify that every kernel is Red Hat one
    # We end up with an empty last item in the list due to a trailing whitespace,
    # therefore we only verify non-empty items in the list comprehension (`if kernel`)
    assert all("Red Hat" in kernel for kernel in installed_kernels if kernel)
