import os

import pytest


@pytest.mark.reboot_after_conversion
def test_reboot(shell):
    if os.environ["TMT_REBOOT_COUNT"] == "0":
        shell("tmt-reboot -t 600")
