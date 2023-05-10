import os

import pytest


@pytest.mark.test_check_data_collection
def test_check_data_collection():
    """
    Verify, that convert2rhel.facts data are not collected, when CONVERT2RHEL_DISABLE_TELEMETRY envar is set.
    Also verify, the file is present, when the environment variable is not set
    """
    convert2rhel_facts_file = "/etc/rhsm/facts/convert2rhel.facts"
    if os.getenv("CONVERT2RHEL_DISABLE_TELEMETRY") and os.environ["CONVERT2RHEL_DISABLE_TELEMETRY"] == "1":
        assert not os.path.exists(convert2rhel_facts_file)
    else:
        assert os.path.exists(convert2rhel_facts_file)
