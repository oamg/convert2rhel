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

import logging
import textwrap

from convert2rhel import utils
from convert2rhel.actions import find_actions_of_severity, format_report_message, format_report_section_heading
from convert2rhel.logger import bcolors, colorize


logger = logging.getLogger(__name__)

#: Map Status codes (from convert2rhel.actions.STATUS_CODE) to color name (from
#: convert2rhel.logger.bcolor)

_STATUS_TO_COLOR = {
    # SUCCESS
    0: "OKGREEN",
    # WARNING
    51: "WARNING",
    # SKIP
    101: "FAIL",
    # OVERRIDABLE
    152: "FAIL",
    # ERROR
    202: "FAIL",
}


def summary(results, include_all_reports=False, with_colors=True):
    """Output a summary regarding the actions execution.

    This summary is intended to be used to inform the user about the results
    reported by the actions.

    .. note:: Expected results format is as following
        {
            "$Action_id": {
                "status": int,
                "error_id": "$error_id",
                "message": None or "$message"
            },
        }

    .. important:: Cases where the summary will be used
        * All action_id have results that are successes (best case possible)
            * If everything is a success, we just output a different message
                for the user.
        * Some action_id have results that are not successes (warnings, errors...)
            * For those cases, we only want to print whatever is higher than
                STATUS_CODE['WARNING']
            * If we print something, let's try to use the correct logger
                instead of just relying on `info`
            * If one of the status has no corresponding logger function, we
                should use just `info`

        The order of the message is from the highest priority (ERROR) to the
        lowest priority (WARNING).

        Message example's::
            * (ERROR) SubscribeSystem.ERROR: Error message
            * (SKIP) SubscribeSystem.SKIP: Skip message
            * (WARNING) SubscribeSystem.WARNING: Warning message

        In case of `message` being empty (as it is optional for some cases), a
        default message will be used::
            * (ERROR) SubscribeSystem.ERROR: [No further information given]

        In case of all actions executed without warnings or errors, the
        following message is used::
            * No problems detected during the analysis!

    :param results: Results dictionary as returned by :func:`run_actions`
    :type results: Mapping
    :keyword with_colors: Whether to color the messages according to their status
    :type with_colors: bool
    :keyword include_all_reports: If all reports should be logged instead of the
        highest ones.
    :type include_all_reports: bool
    """
    logger.task("Conversion analysis report")

    if include_all_reports:
        results = results.items()
    else:
        results = find_actions_of_severity(results, "WARNING")

    terminal_size = utils.get_terminal_size()
    word_wrapper = textwrap.TextWrapper(subsequent_indent="    ", width=terminal_size[0])
    # Sort the results in reverse order, this way, the most important messages
    # will be on top.
    results = sorted(results, key=lambda item: item[1]["status"], reverse=True)

    report = []
    last_status = ""
    for action_id, result in results:
        if last_status != result["status"]:
            report.append("")
            report.append(format_report_section_heading(result["status"]))
            last_status = result["status"]

        entry = format_report_message(result["status"], action_id, result["error_id"], result["message"])
        entry = word_wrapper.fill(entry)
        if with_colors:
            entry = colorize(entry, _STATUS_TO_COLOR[result["status"]])
        report.append(entry)

    # If there is no other message sent to the user, then we just give a
    # happy message to them.
    if not results:
        report.append("No problems detected during the analysis!")

    logger.info("\n".join(report))
