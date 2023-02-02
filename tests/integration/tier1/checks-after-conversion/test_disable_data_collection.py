import os

import pytest


@pytest.mark.disable_data_collection
def test_disable_data_collection():
    """
    Verify, that convert2rhel.facts data are not collected, when CONVERT2RHEL_DISABLE_TELEMETRY envar is set.
    """
    convert2rhel_facts_file = "/etc/rhsm/facts/convert2rhel.facts"
    assert not os.path.exists(convert2rhel_facts_file)
