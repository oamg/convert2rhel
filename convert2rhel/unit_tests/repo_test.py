# -*- coding: utf-8 -*-
#
# Copyright(C) 2016 Red Hat, Inc.
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

import os

import pytest
import six

from convert2rhel import exceptions, repo
from convert2rhel.unit_tests.conftest import centos7, centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock, urllib


@pytest.mark.parametrize(
    ("is_eus_release", "expected"),
    (
        (
            True,
            [
                "rhel-8-for-x86_64-baseos-eus-rpms",
                "rhel-8-for-x86_64-appstream-eus-rpms",
            ],
        ),
        (
            False,
            [
                "rhel-8-for-x86_64-baseos-rpms",
                "rhel-8-for-x86_64-appstream-rpms",
            ],
        ),
    ),
)
@centos8
def test_get_rhel_repoids_el8(pretend_os, is_eus_release, expected, monkeypatch):
    monkeypatch.setattr(repo.system_info, "eus_system", value=is_eus_release)
    repos = repo.get_rhel_repoids()
    assert repos == expected


@pytest.mark.parametrize(
    ("is_els_release", "expected"),
    (
        (
            True,
            [
                "rhel-7-server-els-rpms",
            ],
        ),
        (
            False,
            [
                "rhel-7-server-rpms",
            ],
        ),
    ),
)
@centos7
def test_get_rhel_repoids_el7(pretend_os, is_els_release, expected, monkeypatch):
    monkeypatch.setattr(repo.system_info, "els_system", value=is_els_release)
    repos = repo.get_rhel_repoids()
    assert repos == expected


@pytest.mark.parametrize(("enablerepo", "disablerepos"), (([], ["rhel*"]), (["test-repo"], ["rhel*", "test-repo"])))
def test_get_rhel_repos_to_disable(monkeypatch, enablerepo, disablerepos):
    monkeypatch.setattr(repo.tool_opts, "enablerepo", enablerepo)

    repos = repo.get_rhel_repos_to_disable()

    assert repos == disablerepos


@pytest.mark.parametrize(
    ("disable_repos", "command"),
    (
        ([], ""),
        (["test-repo"], "--disablerepo=test-repo"),
        (["rhel*", "test-repo"], "--disablerepo=rhel* --disablerepo=test-repo"),
    ),
)
def test_get_rhel_disable_repos_command(disable_repos, command):
    output = repo.get_rhel_disable_repos_command(disable_repos)

    assert output == command


class URLOpenMock:
    def __init__(self, url, timeout, contents):
        self.url = url
        self.timeout = timeout
        self.contents = contents

    def __call__(self, *args, **kwds):
        return self

    def read(self):
        return self.contents

    def close(self):
        pass


def test_download_repofile(monkeypatch, tmpdir, caplog):
    monkeypatch.setattr(repo.urllib.request, "urlopen", URLOpenMock(url=None, timeout=1, contents=b"test_file"))
    tmp_dir = str(tmpdir)
    monkeypatch.setattr(repo, "TMP_DIR", tmp_dir)

    filepath = repo.download_repofile("https://test")
    assert os.path.exists(filepath)
    with open(filepath) as f:
        assert f.read() == "test_file\n"
    assert "Successfully downloaded the requested repofile from https://test" in caplog.records[-1].message


def test_download_repofile_urlerror(monkeypatch):
    monkeypatch.setattr(repo.urllib.request, "urlopen", mock.Mock(side_effect=urllib.error.URLError(reason="test")))

    with pytest.raises(exceptions.CriticalError):
        repo.download_repofile("https://test")


def test_write_temporary_repofile(tmpdir, monkeypatch):
    tmp_dir = str(tmpdir)
    monkeypatch.setattr(repo, "TMP_DIR", tmp_dir)
    filepath = repo.write_temporary_repofile("test")

    assert os.path.exists(filepath)
    with open(filepath) as f:
        assert f.read() == "test\n"


def test_write_temporary_repofile_oserror(tmpdir, monkeypatch, caplog):
    monkeypatch.setattr(repo, "TMP_DIR", str(tmpdir))
    monkeypatch.setattr(repo, "store_content_to_file", mock.Mock(side_effect=OSError("test")))

    filepath = repo.write_temporary_repofile("test")

    assert not filepath
    assert "OSError(None): None" in caplog.records[-1].message
