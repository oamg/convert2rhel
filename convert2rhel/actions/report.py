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

from convert2rhel.actions import STATUS_CODE


logger = logging.getLogger(__name__)


_STATUS_NAME_FROM_CODE = dict((value, key) for key, value in actions.STATUS_CODE.items())


def _format_report_message(template, status_name, action_id, error_id, message):
    """Helper function to format the report message.

    :param template: The template to be formatted and returned to the caller.
    :type template: str
    :param status_name: The status name that will be used in the template.
    :type status_name: str
    :param action_id: Action id for the report
    :type action_id: str
    :param error_id: Error id associated with the action
    :type error_id: str
    :param message: The message that was produced in the action
    :type message: str

    :return: The formatted message that will be logged to the user.
    :rtype: str
    """
    # `error_id` and `message` may not be present everytime, since it
    # can be empty (either by mistake, or, intended), we only want to
    # apply these fields if they are present, with a special mention to
    # `message`.
    if error_id:
        template += ".{ERROR_ID}"

    # Special case for `message` to not output empty message to the
    # user without message.
    if message:
        template += ": {MESSAGE}"
    else:
        template += ": [No further information given]"

    return template.format(
        STATUS=status_name,
        ACTION_ID=action_id,
        ERROR_ID=error_id,
        MESSAGE=message,
    )


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

        The order of the message is from the highest priority (FATAL) to the
        lowest priority (WARNING).

        Message example's::
            * (FATAL) SubscribeSystem.FATAL: Fatal error message
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
    # Sort the results in reverse order, this way, the most important messages
    # will be on top.
    results = sorted(results.items(), key=lambda item: item[1]["status"], reverse=True)

    has_report_message = False
    template = "({STATUS}) {ACTION_ID}"

    for action_id, result in results:
        status_name = _STATUS_NAME_FROM_CODE[result["status"]]
        message = _format_report_message(template, status_name, action_id, result["error_id"], result["message"])

        if include_all_reports:
            has_report_message = True
            logger.info(message)
        elif result["status"] >= STATUS_CODE["WARNING"]:
            has_report_message = True
            logger.info(message)

    # If there is no other message sent to the user, then we just give a
    # happy message to them.
    if not has_report_message:
        logger.info("No problems detected during the analysis!")
