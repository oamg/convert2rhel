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

from convert2rhel.actions import find_actions_of_severity, format_report_message


logger = logging.getLogger(__name__)


def summary(results, include_all_reports=False):
    """Output a summary regarding the actions execution.

    This summary is intended to be used to inform the user about the results
    reported by the actions.

    .. note:: Expected results format is as following
        {
            "$Action_id": {
                "status": int,
                "error_id": "$error_id",
                "message": "" or "$message"
            },
        }

    .. important:: Cases where the summary will be used
        * All action_id have results that are successes (best case possible)
            * If everything is a success, we just output a different message
                for the user.
        * Some action_id have results that are not successes (warnings, errors...)
            * For thoe cases, we only want to print whatever is higher than
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
    :param include_all_reports: If all reports should be logged instead of the
        highest ones.
    :type include_all_reports: bool
    """
    logger.task("Conversion analysis report")

    if include_all_reports:
        results = results.items()
    else:
        results = find_actions_of_severity(results, "WARNING")

    # Sort the results in reverse order, this way, the most important messages
    # will be on top.
    results = sorted(results, key=lambda item: item[1]["status"], reverse=True)

    for action_id, result in results:
        message = format_report_message(result["status"], action_id, result["error_id"], result["message"])
        logger.info(message)

    # If there is no other message sent to the user, then we just give a
    # happy message to them.
    if not results:
        logger.info("No problems detected during the analysis!")
