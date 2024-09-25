# -*- coding: utf-8 -*-
#
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
import six

from convert2rhel import actions, systeminfo, toolopts
from convert2rhel.actions.post_conversion import hostmetering
from convert2rhel.systeminfo import Version, system_info
from convert2rhel.unit_tests import RunSubprocessMocked, assert_actions_result, run_subprocess_side_effect


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def hostmetering_instance():
    return hostmetering.ConfigureHostMetering()


@pytest.mark.parametrize(
    ("rhsm_facts", "os_version", "should_configure_metering", "envvar", "managed_service"),
    (
        (
            {},
            Version(7, 9),
            False,  # not on hyperscalershould_configure_metering
            "auto",
            False,
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            True,
            "auto",
            True,
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            True,
            "auto",
            False,  # host-metering service should be running, but isn't
        ),
        (
            {"azure_instance_id": "012345678-abcde-efgh-1234-abcdefgh1234"},
            Version(7, 9),
            True,
            "auto",
            True,
        ),
        (
            {"gcp_instance_id": "12345-6789-abcd-efgh-0123456789ab"},
            Version(7, 9),
            True,
            "auto",
            True,
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(8, 8),
            False,  # not on RHEL 7
            "auto",
            False,
        ),
        (
            {"azure_instance_id": "012345678-abcde-efgh-1234-abcdefgh1234"},
            Version(8, 8),
            False,  # not on RHEL 7
            "auto",
            False,
        ),
        (
            {"gcp_instance_id": "12345-6789-abcd-efgh-0123456789ab"},
            Version(8, 8),
            False,  # not on RHEL 7
            "auto",
            False,
        ),
        (
            {},
            Version(7, 9),
            True,  # forced
            "force",
            True,
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(8, 8),
            True,  # forced
            "force",
            True,
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            False,
            "arbitrary",  # unknown option
            False,
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            False,
            "",  # option left empty
            False,
        ),
    ),
)
def test_configure_host_metering(
    monkeypatch,
    rhsm_facts,
    os_version,
    should_configure_metering,
    envvar,
    hostmetering_instance,
    managed_service,
    global_tool_opts,
):
    monkeypatch.setattr(toolopts, "tool_opts", global_tool_opts)
    monkeypatch.setenv("CONVERT2RHEL_CONFIGURE_HOST_METERING", envvar)
    monkeypatch.setattr(system_info, "version", os_version)
    monkeypatch.setattr(hostmetering, "get_rhsm_facts", mock.Mock(return_value=rhsm_facts))
    yum_mock = mock.Mock(return_value=(0, ""))
    monkeypatch.setattr(hostmetering, "call_yum_cmd", yum_mock)
    subprocess_mock = RunSubprocessMocked(return_string="mock")
    monkeypatch.setattr(hostmetering, "run_subprocess", subprocess_mock)
    monkeypatch.setattr(
        hostmetering.systeminfo,
        "is_systemd_managed_service_running",
        lambda name: managed_service,
    )

    ret = hostmetering_instance.run()

    if should_configure_metering:
        # The return code is true only if the host metering should be
        # configured and the service is running
        assert ret is (should_configure_metering and managed_service)
        yum_mock.assert_called_once_with("install", ["host-metering"])
        subprocess_mock.assert_any_call(["systemctl", "enable", "host-metering.service"])
        subprocess_mock.assert_any_call(["systemctl", "start", "host-metering.service"])
    else:
        assert not ret, "Should not configure host-metering."
        assert yum_mock.call_count == 0, "Should not install anything."
        assert subprocess_mock.call_count == 0, "Should not configure anything."

    if not managed_service and should_configure_metering:
        assert_actions_result(
            hostmetering_instance,
            level="ERROR",
            id="HOST_METERING_NOT_RUNNING",
            title="Host metering service is not running.",
            description="host-metering.service is not running.",
            remediations="You can try to start the service manually"
            " by running following command:\n"
            " - `systemctl start host-metering.service`",
        )


@pytest.mark.parametrize(
    (
        "env_var",
        "os_version",
        "running_on_hyperscaler",
        "install_hostmetering",
        "enable_host_metering_service",
        "service_running",
        "action_message",
        "action_result",
    ),
    (
        (
            "auto",
            Version(8, 8),
            True,
            (None, 0),
            ("", ""),
            False,
            set(
                (
                    actions.ActionMessage(
                        level="INFO",
                        id="CONFIGURE_HOST_METERING_SKIP",
                        title="Did not perform host metering configuration.",
                        description="Host metering is supportted only for RHEL 7.",
                    ),
                ),
            ),
            actions.ActionResult(level="SUCCESS", id="SUCCESS"),
        ),
        (
            "force",
            Version(8, 8),
            False,
            (None, 0),
            ("", ""),
            True,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="FORCED_CONFIGURE_HOST_METERING",
                        title="The `force' option has been used for the CONVERT2RHEL_CONFIGURE_HOST_METERING environment variable.",
                        description="Please note that this option is mainly used for testing and"
                        " will configure host-metering unconditionally."
                        " For generic usage please use the 'auto' option.",
                    ),
                ),
            ),
            actions.ActionResult(level="SUCCESS", id="SUCCESS"),
        ),
        (
            "wrong_env",
            None,
            None,
            (None, 0),
            ("", ""),
            None,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="UNRECOGNIZED_OPTION_CONFIGURE_HOST_METERING",
                        title="Unrecognized option in CONVERT2RHEL_CONFIGURE_HOST_METERING environment variable.",
                        description="Environment variable wrong_env not recognized.",
                        remediations="Set the option to `auto` value if you want to configure host metering.",
                    ),
                ),
            ),
            actions.ActionResult(level="SUCCESS", id="SUCCESS"),
        ),
        (
            "auto",
            Version(7, 9),
            False,
            (None, 0),
            ("", ""),
            None,
            set(
                (
                    actions.ActionMessage(
                        level="INFO",
                        id="CONFIGURE_HOST_METERING_SKIP",
                        title="Did not perform host metering configuration as not needed.",
                        description="Host metering is not needed on the system.",
                    ),
                ),
            ),
            actions.ActionResult(level="SUCCESS", id="SUCCESS"),
        ),
        (
            "auto",
            Version(7, 9),
            True,
            ("yum install fail", 1),
            ("", ""),
            None,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="INSTALL_HOST_METERING_FAILURE",
                        title="Failed to install host metering package.",
                        description="When installing host metering package an error occurred meaning we can't"
                        " enable host metering on the system.",
                        diagnosis="`yum install host-metering` command returned 1 with message yum install fail",
                        remediations="You can try install and set up the host metering"
                        " manually using following commands:\n"
                        " - `yum install host-metering`\n"
                        " - `systemctl enable host-metering.service`\n"
                        " - `systemctl start host-metering.service`",
                    ),
                )
            ),
            actions.ActionResult(level="SUCCESS", id="SUCCESS"),
        ),
        (
            "auto",
            Version(7, 9),
            True,
            ("", 0),
            ("systemctl enable host-metering.service", "Failed to enable"),
            None,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="CONFIGURE_HOST_METERING_FAILURE",
                        title="Failed to enable and start host metering service.",
                        description="The host metering service failed to start"
                        " successfully and won't be able to keep track.",
                        diagnosis="Command systemctl enable host-metering.service failed with Failed to enable",
                        remediations="You can try set up the host metering"
                        " service manually using following commands:\n"
                        " - `systemctl enable host-metering.service`\n"
                        " - `systemctl start host-metering.service`",
                    ),
                )
            ),
            actions.ActionResult(level="SUCCESS", id="SUCCESS"),
        ),
        (
            "auto",
            Version(7, 9),
            True,
            ("", 0),
            ("", ""),
            False,
            set(()),
            actions.ActionResult(
                level="ERROR",
                id="HOST_METERING_NOT_RUNNING",
                title="Host metering service is not running.",
                description="host-metering.service is not running.",
                remediations="You can try to start the service manually"
                " by running following command:\n"
                " - `systemctl start host-metering.service`",
            ),
        ),
        (
            "auto",
            Version(7, 9),
            True,
            ("", 0),
            ("", ""),
            True,
            set(()),
            actions.ActionResult(level="SUCCESS", id="SUCCESS"),
        ),
    ),
)
def test_configure_host_metering_messages_and_results(
    monkeypatch,
    hostmetering_instance,
    env_var,
    os_version,
    running_on_hyperscaler,
    install_hostmetering,
    enable_host_metering_service,
    service_running,
    action_message,
    action_result,
    global_tool_opts,
):
    """Test outputted report/message in each part of the action."""
    if env_var:
        monkeypatch.setenv("CONVERT2RHEL_CONFIGURE_HOST_METERING", env_var)
    monkeypatch.setattr(system_info, "version", os_version)
    # The facts aren't used during the test run
    monkeypatch.setattr(hostmetering, "get_rhsm_facts", mock.Mock(return_value=None))
    monkeypatch.setattr(
        hostmetering_instance, "is_running_on_hyperscaler", mock.Mock(return_value=running_on_hyperscaler)
    )
    monkeypatch.setattr(hostmetering, "call_yum_cmd", mock.Mock(return_value=install_hostmetering))
    monkeypatch.setattr(
        hostmetering_instance, "_enable_host_metering_service", mock.Mock(return_value=enable_host_metering_service)
    )
    monkeypatch.setattr(systeminfo, "is_systemd_managed_service_running", mock.Mock(return_value=service_running))
    monkeypatch.setattr(toolopts, "tool_opts", global_tool_opts)
    hostmetering_instance.run()

    assert action_message.issuperset(hostmetering_instance.messages)
    assert action_message.issubset(hostmetering_instance.messages)
    assert action_result == hostmetering_instance.result


def test_configure_host_metering_no_env_var(monkeypatch, hostmetering_instance, global_tool_opts):
    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="CONFIGURE_HOST_METERING_SKIP",
                title="Did not perform host metering configuration.",
                description="CONVERT2RHEL_CONFIGURE_HOST_METERING was not set.",
            ),
        ),
    )
    monkeypatch.setattr(hostmetering, "tool_opts", global_tool_opts)

    hostmetering_instance.run()

    assert expected.issuperset(hostmetering_instance.messages)
    assert expected.issubset(hostmetering_instance.messages)
    assert actions.ActionResult(level="SUCCESS", id="SUCCESS") == hostmetering_instance.result


@pytest.mark.parametrize(
    ("rhsm_facts", "expected"),
    (
        ({"aws_instance_id": "23143", "azure_instance_id": "12134", "gcp_instance_id": "34213"}, True),
        ({"aws_instance_id": "23143"}, True),
        ({"azure_instance_id": "12134"}, True),
        ({"gcp_instance_id": "34213"}, True),
        ({"invalid_instance_id": "00001"}, False),
    ),
)
def test_is_running_on_hyperscaler(rhsm_facts, monkeypatch, expected, hostmetering_instance):
    monkeypatch.setattr(hostmetering, "get_rhsm_facts", mock.Mock(return_value=rhsm_facts))
    running_on_hyperscaler = hostmetering_instance.is_running_on_hyperscaler()
    assert running_on_hyperscaler == expected


@pytest.mark.parametrize(
    ("enable_output", "enable_ret_code", "start_output", "start_ret_code", "expected"),
    (
        ("", 0, "", 0, ("", "")),
        ("Enable error", 1, "", 0, ("systemctl enable host-metering.service", "Enable error")),
        ("", 0, "Start error", 1, ("systemctl start host-metering.service", "Start error")),
        ("Enable error", 1, "Start error", 1, ("systemctl enable host-metering.service", "Enable error")),
    ),
)
def test_enable_host_metering_service(
    enable_output,
    enable_ret_code,
    start_output,
    start_ret_code,
    expected,
    monkeypatch,
    hostmetering_instance,
):
    systemctl_enable = ("systemctl", "enable", "host-metering.service")
    systemctl_start = ("systemctl", "start", "host-metering.service")

    # Mock rpm command
    run_subprocess_mock = RunSubprocessMocked(
        side_effect=run_subprocess_side_effect(
            (
                systemctl_enable,
                (
                    enable_output,
                    enable_ret_code,
                ),
            ),
            (systemctl_start, (start_output, start_ret_code)),
        ),
    )
    monkeypatch.setattr(hostmetering, "run_subprocess", value=run_subprocess_mock)

    enable = hostmetering_instance._enable_host_metering_service()

    assert enable == expected
