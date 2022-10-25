import os


def test_temp_folder():
    """Testing, if the temporary folder was sucessfully removed after conversion"""
    tmp_folder = "/var/lib/convert2rhel/"
    assert not os.path.exists(tmp_folder)
