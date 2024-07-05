# Copyright(C) 2024 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__metaclass__ = type

import logging
import os

import pytest

from convert2rhel import unit_tests, utils
from convert2rhel.actions.post_conversion import remove_tmp_dir


@pytest.fixture
def remove_tmp_dir_instance():
    return remove_tmp_dir.RemoveTmpDir()


def test_remove_tmp_dir(remove_tmp_dir_instance, monkeypatch, tmpdir, caplog):
    caplog.set_level(logging.INFO)
    path = str(tmpdir)
    monkeypatch.setattr(remove_tmp_dir_instance, "tmp_dir", path)
    assert os.path.isdir(path)
    remove_tmp_dir_instance.run()
    assert "Temporary folder " + str(path) + " removed" in caplog.text
    assert not os.path.isdir(path)


def test_remove_tmp_dir_non_existent(remove_tmp_dir_instance, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    path = "/tmp/this/path/is/unlikely/to/exist"
    monkeypatch.setattr(remove_tmp_dir_instance, "tmp_dir", path)
    assert not os.path.isdir(path)
    remove_tmp_dir_instance.run()
    assert "Temporary folder " + str(path) + " removed" not in caplog.text


def test_remove_tmp_dir_failure(remove_tmp_dir_instance, monkeypatch, tmpdir, caplog):
    caplog.set_level(logging.INFO)
    path = str(tmpdir)
    monkeypatch.setattr(remove_tmp_dir_instance, "tmp_dir", path)
    assert os.path.isdir(path)
    os.chmod(path, 0)
    remove_tmp_dir_instance.run()
    expected_message = (
        "The folder %s is left untouched. You may remove the folder manually"
        " after you ensure there is no preserved data you would need." % path
    )
    assert expected_message in caplog.text
    os.chmod(path, 0o755)


def test_remove_tmp_dir_nonempty(remove_tmp_dir_instance, monkeypatch, tmpdir, caplog):
    caplog.set_level(logging.INFO)
    path = str(tmpdir)
    monkeypatch.setattr(remove_tmp_dir_instance, "tmp_dir", path)
    assert os.path.isdir(path)
    with open(os.path.join(path, "remove_tmp_dir_test"), "w") as fp:
        fp.write("This is a file in the temporary directory.\n")
    remove_tmp_dir_instance.run()
    assert "Temporary folder " + str(path) + " removed" in caplog.text
    assert not os.path.isdir(path)
