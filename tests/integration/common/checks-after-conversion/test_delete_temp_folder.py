import os


def test_deleted_temporary_folder():
    """
    Verify the temporary folder "/var/lib/convert2rhel/" was successfully removed after the conversion.
    """
    tmp_folder = "/var/lib/convert2rhel/"
    assert not os.path.exists(tmp_folder)
