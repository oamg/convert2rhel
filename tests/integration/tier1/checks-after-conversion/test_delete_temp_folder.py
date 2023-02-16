import os

import pytest


@pytest.mark.delete_temporary_folder
def test_temp_folder():
    """Testing, if the temporary folder was successfully removed after conversion"""
    tmp_folder = "/var/lib/convert2rhel/"
    assert not os.path.exists(tmp_folder)
