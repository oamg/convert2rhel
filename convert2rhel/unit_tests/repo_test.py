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

from convert2rhel import exceptions, repo
from convert2rhel.unit_tests.conftest import centos7, centos8

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


@pytest.mark.parametrize(
    ("disable_repos", "command"),
    (
        ([], []),
        (["test-repo"], ["--disablerepo=test-repo"]),
        (["rhel*", "test-repo"], ["--disablerepo=rhel*", "--disablerepo=test-repo"]),
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


class TestDownloadRepofile:
    def test_download_repofile(self, monkeypatch, tmpdir, caplog):
        monkeypatch.setattr(repo.urllib.request, "urlopen", URLOpenMock(url=None, timeout=1, contents=b"test_file"))
        tmp_dir = str(tmpdir)
        monkeypatch.setattr(repo, "TMP_DIR", tmp_dir)

        contents = repo.download_repofile("https://test")
        assert contents == "test_file"
        assert "Successfully downloaded a repository file from https://test" in caplog.records[-1].message

    def test_failed_to_open_url(self, monkeypatch):
        monkeypatch.setattr(repo.urllib.request, "urlopen", mock.Mock(side_effect=urllib.error.URLError(reason="test")))

        with pytest.raises(exceptions.CriticalError) as execinfo:
            repo.download_repofile("https://test")

        assert "DOWNLOAD_REPOSITORY_FILE_FAILED" in execinfo._excinfo[1].id
        assert "Failed to download a repository file" in execinfo._excinfo[1].title
        assert "test" in execinfo._excinfo[1].description

    def test_no_contents_in_request_url(self, monkeypatch):
        monkeypatch.setattr(
            repo.urllib.request, "urlopen", mock.Mock(return_value=URLOpenMock(url="", timeout=1, contents=b""))
        )

        with pytest.raises(exceptions.CriticalError) as execinfo:
            repo.download_repofile("https://test")

        assert "REPOSITORY_FILE_EMPTY_CONTENT" == execinfo._excinfo[1].id
        assert "No content available in a repository file" in execinfo._excinfo[1].title
        assert "The requested repository file seems to be empty." in execinfo._excinfo[1].description


def test_write_temporary_repofile(tmpdir, monkeypatch):
    tmp_dir = str(tmpdir)
    monkeypatch.setattr(repo, "TMP_DIR", tmp_dir)
    filepath = repo.write_temporary_repofile("test")

    assert os.path.exists(filepath)
    with open(filepath) as f:
        assert f.read() == "test\n"


def test_write_temporary_repofile_mkdir_failure(monkeypatch):
    monkeypatch.setattr(repo.tempfile, "mkdtemp", mock.Mock(side_effect=OSError("unable")))

    with pytest.raises(exceptions.CriticalError) as execinfo:
        repo.write_temporary_repofile("test")

    assert "CREATE_TMP_DIR_FOR_REPOFILES_FAILED" in execinfo._excinfo[1].id
    assert "Failed to create a temporary directory" in execinfo._excinfo[1].title
    assert "unable" in execinfo._excinfo[1].description


def test_write_temporary_repofile_store_failure(tmpdir, monkeypatch):
    monkeypatch.setattr(repo, "TMP_DIR", str(tmpdir))
    monkeypatch.setattr(repo, "store_content_to_file", mock.Mock(side_effect=OSError("test")))

    with pytest.raises(exceptions.CriticalError) as execinfo:
        repo.write_temporary_repofile("test")

    assert "STORE_REPOFILE_FAILED" in execinfo._excinfo[1].id
    assert "Failed to store a repository file" in execinfo._excinfo[1].title
    assert "test" in execinfo._excinfo[1].description


class TestDisableReposDuringAnalysis:
    def test_singleton(self, monkeypatch):
        """Test if the singleton works properly and only 1 instance is created."""
        # Force remove the singleton instance
        repo.DisableReposDuringAnalysis._instance = None

        get_rhel_repos_to_disable = mock.Mock()
        monkeypatch.setattr(repo.DisableReposDuringAnalysis, "_set_rhel_repos_to_disable", get_rhel_repos_to_disable)

        singleton1 = repo.DisableReposDuringAnalysis()
        singleton2 = repo.DisableReposDuringAnalysis()

        assert singleton1 is singleton2
        assert get_rhel_repos_to_disable.call_count == 1

        # Force remove the singleton instance
        repo.DisableReposDuringAnalysis._instance = None

    @pytest.mark.parametrize(
        ("disable_repos", "yum_output", "result"),
        (
            (
                ["repo1", "repo2", "repo3"],
                [
                    (
                        """Loading "fastestmirror" plugin
                        Config time: 0.003


                        Error getting repository data for repo1, repository not found""",
                        1,
                    ),
                    ("", 0),
                ],
                ["repo2", "repo3"],
            ),
            ([], "Some testing output, won't be called", []),
            (["repo1", "repo2"], [("Message causing exit code 1", 1)], ["repo1", "repo2"]),
            (
                ["repo1"],
                [("All fine", 0)],
                ["repo1"],
            ),
        ),
    )
    def test_get_valid_custom_repos(self, yum_output, disable_repos, result, monkeypatch):
        """Test parsing of the yum output and getting the unavailable repositories."""
        monkeypatch.setattr(repo, "call_yum_cmd", mock.Mock(side_effect=yum_output))

        output = repo._get_valid_custom_repos(disable_repos)

        assert output == result

    @pytest.mark.parametrize(
        ("no_rhsm", "enablerepo", "disablerepos"),
        (
            (False, [], ["rhel*"]),
            (True, ["test-repo"], ["rhel*", "test-repo"]),
            (True, [], ["rhel*"]),
            (False, ["test-repo"], ["rhel*"]),
        ),
    )
    def test_get_rhel_repos_to_disable_dnf(self, monkeypatch, global_tool_opts, no_rhsm, enablerepo, disablerepos):
        """Test getting the repositories to be disabled on systems with DNF. On DNF there is no need to check if
        repositories for disabling are accessible. The package manager handles it well.
        """
        # Force remove the singleton instance
        repo.DisableReposDuringAnalysis._instance = None

        monkeypatch.setattr(repo, "tool_opts", global_tool_opts)
        monkeypatch.setattr(repo, "TYPE", "dnf")
        global_tool_opts.enablerepo = enablerepo
        global_tool_opts.no_rhsm = no_rhsm

        repos = repo.DisableReposDuringAnalysis().repos_to_disable
        assert repos == disablerepos

        # Force remove the singleton instance
        repo.DisableReposDuringAnalysis._instance = None

    @pytest.mark.parametrize(
        ("no_rhsm", "enablerepo", "disablerepos"),
        (
            (False, [], ["rhel*"]),
            (True, ["test-repo"], ["rhel*", "test-repo"]),
            (True, [], ["rhel*"]),
            (False, ["test-repo"], ["rhel*"]),
        ),
    )
    def test_get_rhel_repos_to_disable_yum(self, monkeypatch, global_tool_opts, no_rhsm, enablerepo, disablerepos):
        """Test getting the repositories to be disabled on systems with YUM. With YUM all the repositories needs
        to be accessible.
        """
        # Force remove the singleton instance
        repo.DisableReposDuringAnalysis._instance = None

        monkeypatch.setattr(repo, "tool_opts", global_tool_opts)
        monkeypatch.setattr(repo, "TYPE", "yum")
        # Set the output of yum makecache empty (no problem, simulating the inaccessible repo is in different test)
        monkeypatch.setattr(repo, "call_yum_cmd", mock.Mock(return_value=("", 0)))
        global_tool_opts.enablerepo = enablerepo
        global_tool_opts.no_rhsm = no_rhsm

        repos = repo.DisableReposDuringAnalysis().repos_to_disable
        assert repos == disablerepos

        # Force remove the singleton instance
        repo.DisableReposDuringAnalysis._instance = None
