import os

import pytest


@pytest.mark.test_check_data_collection
def test_check_data_collection():
    """
    Verify that after conversion the convert2rhel.facts file is present.
    """
    convert2rhel_facts_file = "/etc/rhsm/facts/convert2rhel.facts"
    assert os.path.exists(convert2rhel_facts_file)
