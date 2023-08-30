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

import copy
import json
import logging
import textwrap

from convert2rhel import utils
from convert2rhel.actions import (
    _STATUS_HEADER,
    _STATUS_NAME_FROM_CODE,
    find_actions_of_severity,
    format_action_status_message,
    level_for_combined_action_data,
)
from convert2rhel.logger import colorize


logger = logging.getLogger(__name__)

#: The filename to store the results of running preassessment
CONVERT2RHEL_JSON_RESULTS = "/var/log/convert2rhel/convert2rhel-pre-conversion.json"

#: Map Status codes (from convert2rhel.actions.STATUS_CODE) to color name (from
#: convert2rhel.logger.bcolor)

_STATUS_TO_COLOR = {
    # SUCCESS
    0: "OKGREEN",
    # INFO
    25: "INFO",
    # WARNING
    51: "WARNING",
    # SKIP
    101: "FAIL",
    # OVERRIDABLE
    152: "FAIL",
    # ERROR
    202: "FAIL",
}


def summary_as_json(results, json_file=CONVERT2RHEL_JSON_RESULTS):
    """
    Output the results as a json_file.

    :param results: The results from the Actions which have been run.
    :type results: dict
    :keyword json_file: Filename of a file to write the json results to.
    :type json_file: str

    The json output is a slight modification to the results data that is passed in:

    * The outermost container is a dictionary.  The current two fields are:
        :format_version: This is currently "1.0".  It will be increased
            whenever the version changes.
        :actions: This contains a modified copy of the results

    * The results are modified so that status codes use their symbolic names
      instead of the numeric values.
    """
    # Use an envelope so we can add other, non-result info if necessary.
    envelope = {
        "format_version": "1.0",
        "actions": copy.deepcopy(results),
    }

    # Use the symbolic name in the json output
    for action in envelope["actions"].values():
        action["result"]["level"] = _STATUS_NAME_FROM_CODE[action["result"]["level"]]

        for message in action["messages"]:
            message["level"] = _STATUS_NAME_FROM_CODE[message["level"]]

    with open(json_file, "w") as f:
        json.dump(envelope, f)


def summary(results, include_all_reports=False, with_colors=True):
    """Output a summary regarding the actions execution.

    This summary is intended to be used to inform the user about the results
    reported by the actions.

    .. note:: Expected results format is as following
        {
            "$Action_id": {
                "messages" : [{"level": int, "id": "$id", "message": None or "$message"}],
                "result" : {
                    "level": int,
                    "id": "$id",
                    "message": "" or "$message"
                }
            },
        }

    .. important:: Cases where the summary will be used
        * All action_id have results that are successes (best case possible)
            * If everything is a success, we just output a different message
                for the user.
        * Some action_id have results that are not successes (warnings, errors...)
            * For those cases, we only want to print whatever is higher than
                STATUS_CODE['WARNING']

        The order of the message is from the highest priority (ERROR) to the
        lowest priority (WARNING).

        Message example's::
            * (ERROR) SubscribeSystem.ERROR: Error message
            * (SKIP) SubscribeSystem.SKIP: Skip message
            * (OVERRIDABLE) SubscribeSystem.OVERRIDABLE: overridable message

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
    logger.task("Pre-conversion analysis report")
    combined_results_and_message = {}
    report = []

    for action_id, action_value in results.items():
        combined_results_and_message[(action_id, action_value["result"]["id"])] = {
            "level": action_value["result"]["level"],
            "message": action_value["result"]["message"],
        }
        for message in action_value["messages"]:
            combined_results_and_message[(action_id, message["id"])] = {
                "level": message["level"],
                "message": message["message"],
            }

    if include_all_reports:
        combined_results_and_message = combined_results_and_message.items()

    else:
        combined_results_and_message = find_actions_of_severity(
            combined_results_and_message, "WARNING", level_for_combined_action_data
        )
    terminal_size = utils.get_terminal_size()
    word_wrapper = textwrap.TextWrapper(subsequent_indent="    ", width=terminal_size[0], replace_whitespace=False)
    # Sort the results in reverse order, this way, the most important messages
    # will be on top.
    combined_results_and_message = sorted(combined_results_and_message, key=lambda item: item[1]["level"], reverse=True)

    last_level = ""
    for message_id, combined_result in combined_results_and_message:
        if last_level != combined_result["level"]:
            report.append("")
            report.append(format_report_section_heading(combined_result["level"]))
            last_level = combined_result["level"]

        entry = format_action_status_message(
            combined_result["level"], message_id[0], message_id[1], combined_result["message"]
        )
        entry = word_wrapper.fill(entry)
        if with_colors:
            entry = colorize(entry, _STATUS_TO_COLOR[combined_result["level"]])
        report.append(entry)

    # If there is no other message sent to the user, then we just give a
    # happy message to them.
    if not combined_results_and_message:
        report.append("No problems detected during the analysis!")

    logger.info("%s\n" % "\n".join(report))


def format_report_section_heading(status_code):
    """
    Format a section heading for a status in the report.

    :param status_code: The status code that will be used in the heading
    :type status_code: int
    :return: The formatted heading that the caller can log.
    :rtype: str
    """
    status_header = _STATUS_HEADER[status_code]
    highlight = "=" * 10

    heading = "{highlight} {status_header} {highlight}".format(highlight=highlight, status_header=status_header)
    return heading
