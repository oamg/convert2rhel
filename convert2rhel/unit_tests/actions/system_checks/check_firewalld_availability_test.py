# Copyright(C) 2023 Red Hat, Inc.
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

import pytest

from convert2rhel import pkgmanager, unit_tests
from convert2rhel.actions.system_checks import check_firewalld_availability
from convert2rhel.systeminfo import Version
from convert2rhel.unit_tests.conftest import oracle8


@pytest.fixture
def check_firewalld_availability_is_running_action():
    return check_firewalld_availability.CheckFirewalldAvailability()


@pytest.fixture
def write_firewalld_mockup_config(tmpdir, request):
    config_file = tmpdir.join("firewalld.conf")
    config_file_path = str(config_file)
    if not request.param["content"]:
        return config_file_path

    config_file.write(request.param["content"])
    return config_file_path


@pytest.mark.parametrize(
    ("write_firewalld_mockup_config", "expected"),
    (
        (
            {
                "content": """
CleanupModulesOnExit=YeS
"""
            },
            True,
        ),
        (
            {
                "content": """
CleanupModulesOnExit=TrUe
"""
            },
            True,
        ),
        (
            {
                "content": """
CleanupModulesOnExit=yes
"""
            },
            True,
        ),
        (
            {
                "content": """
# firewalld config file

DefaultZone=public

MinimalMark=100

CleanupOnExit=yes

Lockdown=no

IPv6_rpfilter=yes

IndividualCalls=no

LogDenied=off

AutomaticHelpers=system

AllowZoneDrifting=yes
"""
            },
            True,
        ),
        (
            {
                "content": """
# firewalld config file

AllowZoneDrifting=yes

CleanupModulesOnExit=yes
"""
            },
            True,
        ),
        (
            {
                "content": """
# firewalld config file

AllowZoneDrifting=yes

CleanupModulesOnExit=true
"""
            },
            True,
        ),
        (
            {"content": None},
            True,
        ),
    ),
    indirect=("write_firewalld_mockup_config",),
)
def test_is_modules_cleanup_enabled(monkeypatch, write_firewalld_mockup_config, expected):
    monkeypatch.setattr(check_firewalld_availability, "FIREWALLD_CONFIG_FILE", write_firewalld_mockup_config)
    assert check_firewalld_availability._is_modules_cleanup_enabled() == expected


@pytest.mark.parametrize(
    ("write_firewalld_mockup_config", "option_parsed", "expected"),
    (
        (
            {
                "content": """
#CleanupModulesOnExit=yes
"""
            },
            False,
            True,
        ),
        (
            {
                "content": """
;CleanupModulesOnExit=yes
"""
            },
            False,
            True,
        ),
        (
            {
                "content": """
;CleanupModulesOnExit=yes
CleanupModulesOnExit=yes
"""
            },
            True,
            True,
        ),
        (
            {
                "content": """
#CleanupModulesOnExit=yes
CleanupModulesOnExit=yes
"""
            },
            True,
            True,
        ),
    ),
    indirect=("write_firewalld_mockup_config",),
)
def test_is_modules_cleanup_config_commented(
    monkeypatch, write_firewalld_mockup_config, option_parsed, expected, caplog
):
    monkeypatch.setattr(check_firewalld_availability, "FIREWALLD_CONFIG_FILE", write_firewalld_mockup_config)
    assert check_firewalld_availability._is_modules_cleanup_enabled() == expected

    if not option_parsed:
        assert (
            "Couldn't find CleanupModulesOnExit in firewalld.conf. Treating it as enabled because of default behavior."
            in caplog.records[-1].message
        )
    else:
        assert "CleanupModulesOnExit option enabled" in caplog.records[-1].message


@pytest.mark.skipif(pkgmanager.TYPE == "yum", reason="Test is only relevant for RHEL 8+")
class TestCheckFirewalldAvailabilityAction:
    @pytest.mark.parametrize(
        ("major", "minor", "id"),
        (
            (7, 9, "centos"),
            (7, 9, "oracle"),
            (8, 6, "oracle"),
            (8, 5, "centos"),
        ),
    )
    def test_not_supported_system(
        self, major, minor, id, monkeypatch, global_system_info, check_firewalld_availability_is_running_action, caplog
    ):
        monkeypatch.setattr(check_firewalld_availability, "system_info", global_system_info)
        global_system_info.id = id
        global_system_info.version = Version(major, minor)

        check_firewalld_availability_is_running_action.run()

        assert "Skipping the check as it is relevant only for Oracle Linux 8.8 and above." in caplog.records[-1].message

    @oracle8
    def test_systemd_managed_service_not_running(
        self, pretend_os, global_system_info, monkeypatch, check_firewalld_availability_is_running_action, caplog
    ):
        monkeypatch.setattr(check_firewalld_availability, "system_info", global_system_info)
        global_system_info.id = "oracle"
        global_system_info.version = Version(8, 8)
        monkeypatch.setattr(check_firewalld_availability.system_info, "is_rpm_installed", lambda name: True)
        monkeypatch.setattr(
            check_firewalld_availability.systeminfo, "is_systemd_managed_service_running", lambda name: False
        )
        check_firewalld_availability_is_running_action.run()
        assert "Firewalld service reported that it is not running." in caplog.records[-1].message

    @oracle8
    def test_firewalld_rpm_not_installed(
        self, pretend_os, global_system_info, monkeypatch, check_firewalld_availability_is_running_action, caplog
    ):
        monkeypatch.setattr(check_firewalld_availability, "system_info", global_system_info)
        global_system_info.id = "oracle"
        global_system_info.version = Version(8, 8)
        monkeypatch.setattr(check_firewalld_availability.system_info, "is_rpm_installed", lambda name: False)
        check_firewalld_availability_is_running_action.run()
        assert "The firewalld package is not installed. Nothing to do." in caplog.records[-1].message

    @pytest.mark.parametrize(
        ("write_firewalld_mockup_config",),
        (
            (
                {
                    "content": """
CleanupModulesOnExit=yes
"""
                },
            ),
            (
                {
                    "content": """
CleanupModulesOnExit=true
"""
                },
            ),
            (
                {
                    "content": """
CleanupModulesOnExit=YeS
"""
                },
            ),
            (
                {
                    "content": """
SomethingElse=yes
"""
                },
            ),
        ),
        indirect=("write_firewalld_mockup_config",),
    )
    @oracle8
    def test_cleanup_modules_on_exit_is_true(
        self,
        pretend_os,
        global_system_info,
        check_firewalld_availability_is_running_action,
        write_firewalld_mockup_config,
        monkeypatch,
    ):
        monkeypatch.setattr(check_firewalld_availability, "system_info", global_system_info)
        global_system_info.id = "oracle"
        global_system_info.version = Version(8, 8)
        monkeypatch.setattr(check_firewalld_availability, "FIREWALLD_CONFIG_FILE", write_firewalld_mockup_config)
        monkeypatch.setattr(
            check_firewalld_availability.systeminfo,
            "is_systemd_managed_service_running",
            lambda name: True,
        )
        monkeypatch.setattr(
            check_firewalld_availability.system_info,
            "is_rpm_installed",
            lambda name: True,
        )
        check_firewalld_availability_is_running_action.run()
        unit_tests.assert_actions_result(
            check_firewalld_availability_is_running_action,
            level="ERROR",
            id="FIREWALLD_MODULES_CLEANUP_ON_EXIT_CONFIG",
            title="Firewalld is set to cleanup modules after exit.",
            description="Firewalld running on Oracle Linux 8 can lead to a conversion failure.",
            diagnosis=(
                "We've detected that firewalld unit is running and that causes iptables and nftables "
                "failures on Oracle Linux 8 and under certain conditions it can lead to a conversion failure."
            ),
            remediation=(
                "Set the option CleanupModulesOnExit in /etc/firewalld/firewalld.conf "
                "to no prior to running convert2rhel:\n"
                " sed -i -- 's/CleanupModulesOnExit=yes/CleanupModulesOnExit=no/g' /etc/firewalld/firewalld.conf\n && firewall-cmd --reload."
                " You can change the option back to yes after the system reboot "
                "- that is after the system boots into the RHEL kernel."
            ),
        )
