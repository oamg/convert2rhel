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

from convert2rhel.toolopts.config import FileConfig


class TestFileConfig:
    @pytest.mark.parametrize(
        ("content", "expected_message"),
        (
            (
                """\
[subscription_manager]
incorect_option = yes
                """,
                "Unsupported option",
            ),
            (
                """\
[invalid_header]
username = correct_username
                """,
                "Couldn't find header",
            ),
            (
                """\
[subscription_manager]
# username =
                """,
                "No options found for subscription_manager. It seems to be empty or commented.",
            ),
        ),
    )
    def test_options_from_config_files_invalid_head_and_options(self, content, expected_message, tmpdir, caplog):
        path = os.path.join(str(tmpdir), "convert2rhel.ini")

        with open(path, "w") as file:
            file.write(content)
        os.chmod(path, 0o600)

        file_config = FileConfig(path)
        file_config.options_from_config_files()

        assert expected_message in caplog.text

        # Cleanup test file
        os.remove(path)

    @pytest.mark.parametrize(
        ("content", "output"),
        (
            (
                """\
[subscription_manager]
username = correct_username
                """,
                {"username": "correct_username"},
            ),
            (
                """\
[subscription_manager]
username = "correct_username"
                """,
                {"username": '"correct_username"'},
            ),
            (
                """\
[subscription_manager]
password = correct_password
                """,
                {"password": "correct_password"},
            ),
            (
                """\
[subscription_manager]
activation_key = correct_key
password = correct_password
username = correct_username
org = correct_org
                """,
                {
                    "username": "correct_username",
                    "password": "correct_password",
                    "activation_key": "correct_key",
                    "org": "correct_org",
                },
            ),
            (
                """\
[subscription_manager]
org = correct_org
                """,
                {"org": "correct_org"},
            ),
            (
                """\
[inhibitor_overrides]
incomplete_rollback = false
                """,
                {"incomplete_rollback": False},
            ),
            (
                """\
[subscription_manager]
org = correct_org

[inhibitor_overrides]
incomplete_rollback = false
                """,
                {"org": "correct_org", "incomplete_rollback": False},
            ),
            (
                """\
[inhibitor_overrides]
incomplete_rollback = false
tainted_kernel_module_check_skip = false
allow_older_version = false
allow_unavailable_kmods = false
configure_host_metering = false
skip_kernel_currency_check = false
                """,
                {
                    "incomplete_rollback": False,
                    "tainted_kernel_module_check_skip": False,
                    "allow_older_version": False,
                    "allow_unavailable_kmods": False,
                    "configure_host_metering": False,
                    "skip_kernel_currency_check": False,
                },
            ),
            (
                """\
[inhibitor_overrides]
incomplete_rollback = on
                """,
                {
                    "incomplete_rollback": True,
                },
            ),
            (
                """\
[inhibitor_overrides]
incomplete_rollback = 1
                """,
                {
                    "incomplete_rollback": True,
                },
            ),
            (
                """\
[inhibitor_overrides]
incomplete_rollback = yes
                """,
                {
                    "incomplete_rollback": True,
                },
            ),
        ),
    )
    def test_options_from_config_files_default(self, content, output, monkeypatch, tmpdir):
        """Test config files in default path."""
        path = os.path.join(str(tmpdir), "convert2rhel.ini")

        with open(path, "w") as file:
            file.write(content)
        os.chmod(path, 0o600)

        paths = ["/nonexisting/path", path]
        monkeypatch.setattr(FileConfig, "DEFAULT_CONFIG_FILES", value=paths)
        file_config = FileConfig(None)
        opts = file_config.options_from_config_files()
        for key in output.keys():
            assert opts[key] == output[key]

    @pytest.mark.parametrize(
        ("content", "output", "content_lower_priority"),
        (
            (
                """\
[subscription_manager]
username = correct_username
activation_key = correct_key
                """,
                {"username": "correct_username", "password": None, "activation_key": "correct_key", "org": None},
                """\
[subscription_manager]
username = low_prior_username
                """,
            ),
            (
                """\
[subscription_manager]
username = correct_username
activation_key = correct_key
                """,
                {"username": "correct_username", "password": None, "activation_key": "correct_key", "org": None},
                """\
[subscription_manager]
activation_key = low_prior_key
                """,
            ),
            (
                """\
[subscription_manager]
activation_key = correct_key
org = correct_org""",
                {"username": None, "password": None, "activation_key": "correct_key", "org": "correct_org"},
                """\
[subscription_manager]
org = low_prior_org
                """,
            ),
            (
                """\
[subscription_manager]
activation_key = correct_key
Password = correct_password
                """,
                {"username": None, "password": "correct_password", "activation_key": "correct_key", "org": None},
                """\
[subscription_manager]
password = low_prior_pass
                """,
            ),
            (
                """\
[subscription_manager]
activation_key = correct_key
Password = correct_password
                """,
                {"username": None, "password": "correct_password", "activation_key": "correct_key", "org": None},
                """\
[INVALID_HEADER]
password = low_prior_pass
                """,
            ),
            (
                """\
[subscription_manager]
activation_key = correct_key
Password = correct_password
                """,
                {"username": None, "password": "correct_password", "activation_key": "correct_key", "org": None},
                """\
[subscription_manager]
incorrect_option = incorrect_option
                """,
            ),
        ),
    )
    def test_options_from_config_files_specified(self, content, output, content_lower_priority, monkeypatch, tmpdir):
        """Test user specified path for config file."""
        path_higher_priority = os.path.join(str(tmpdir), "convert2rhel.ini")
        with open(path_higher_priority, "w") as file:
            file.write(content)
        os.chmod(path_higher_priority, 0o600)

        path_lower_priority = os.path.join(str(tmpdir), "convert2rhel_lower.ini")
        with open(path_lower_priority, "w") as file:
            file.write(content_lower_priority)
        os.chmod(path_lower_priority, 0o600)

        paths = [path_higher_priority, path_lower_priority]
        monkeypatch.setattr(FileConfig, "DEFAULT_CONFIG_FILES", value=paths)

        file_config = FileConfig(None)
        opts = file_config.options_from_config_files()

        for key in ["username", "password", "activation_key", "org"]:
            if key in opts:
                assert opts[key] == output[key]
