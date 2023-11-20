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


from envparse import env


def test_run_conversion_payg(shell, convert2rhel):
    """
    Verify that --payg installs, enables and starts host-metering service.
        1/ Run conversion with --payg verifying the conversion is not inhibited and completes successfully
        2/ Verify that host-metering is enabled and started
    """
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --payg --debug".format(
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
