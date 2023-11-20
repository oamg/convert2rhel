# -*- coding: utf-8 -*-
#
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

import os

import pytest

from envparse import env


@pytest.fixture
def force_hostmetering_envar():
    os.environ["CONVERT2RHEL_CONFIGURE_HOST_METERING"] = "force"

    yield

    del os.environ["CONVERT2RHEL_CONFIGURE_HOST_METERING"]


def setup_test_metering_endpoint():
    """
    Setup custom metering endpoint to avoid sending data to production

    This url is default remote_write endpoint of Prometheus server, thus if
    something else starts Prometheus in default configuration on the host then
    the data sent can be observed there.

    If no Prometheus is running on the host, then the write will fail but
    the host-metering service will be running. This is still OK from PoV of
    convert2rhel integration test.
    """
    with open("/etc/host-metering.conf", "w") as f:
        f.write(
            """\
[host-metering]
write_url=http://localhost:9090/api/v1/write
"""
        )


def test_run_conversion_metering(shell, convert2rhel, force_hostmetering_envar):
    """
    Verify that convert2rhel automatically installs, enables and starts host-metering
    service on hyperscallers on RHEL 7.9.
    """
    setup_test_metering_endpoint()
    os.environ["CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK"] = "1"
    os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"] = "1"
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
        )
    ) as c2r:
        c2r.expect(
            [
                "Installing host-metering rpms.",
                "Enabling host-metering service.",
                "Starting host-metering service.",
            ]
        )
        assert c2r.expect("Conversion successful") == 0

    assert c2r.exitstatus == 0

    # There should not be any problems in coversion
    assert shell("grep -i 'traceback' /var/log/convert2rhel/convert2rhel.log").returncode == 1
