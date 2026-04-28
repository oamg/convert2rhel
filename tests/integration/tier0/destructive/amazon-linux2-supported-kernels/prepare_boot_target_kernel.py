#!/usr/bin/env python3

import os


def test_upgrade_amzn2_kernel(shell):
    """
    tmt prepare step: install the Amazon Linux 2 kernel line from C2R_AL2_TARGET_KERNEL
    (5.4, 5.10 or 5.15), set GRUB default, and mkconfig. A follow-up ansible reboot applies it.
    """
    target_kernel = os.environ.get("C2R_AL2_TARGET_KERNEL")

    enabled_kernel = shell(
        "amazon-linux-extras | grep -oP 'kernel-[\d.]+=\S+\s+enabled' | grep -oP 'kernel-[\d.]+'"
    ).output.strip()

    if enabled_kernel != target_kernel:
        assert shell(f"amazon-linux-extras disable {enabled_kernel}")

    assert shell(f"amazon-linux-extras install -y {target_kernel}").returncode == 0
    vmlinuz = shell(
        "rpm -q --last kernel | head -1 | cut -d ' ' -f1 | sed 's/kernel-/\/boot\/vmlinux-/'"
    ).output.strip()
    assert shell(f"grubby --set-default {vmlinuz}").returncode == 0
    assert shell("grub2-mkconfig -o /boot/grub2/grub.cfg").returncode == 0
