def test_provisioned_machine(shell):
    assert shell("ip link show").returncode == 0
    # Make sure we have at least 2 non-loopback NICs
    non_loopback_nics = shell("ip -br link show | grep -v LOOPBACK | wc -l")
    assert int(non_loopback_nics.output.strip()) >= 2
