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

__metaclass__ = type

import logging
import re

from six.moves import urllib


loggerinst = logging.getLogger(__name__)


def setup_rhsm_parts(opts):
    rhsm_parts = {}

    if opts.serverurl:
        if opts["no_rhsm"]:
            loggerinst.warning("Ignoring the --serverurl option. It has no effect when --no-rhsm is used.")

        # WARNING: We cannot use the following helper until after no_rhsm,
        # username, password, activation_key, and organization have been
        # set.
        elif not _should_subscribe(opts):
            loggerinst.warning(
                "Ignoring the --serverurl option. It has no effect when no credentials to subscribe the system were given."
            )
        else:
            # Parse the serverurl and save the components.
            try:
                url_parts = _parse_subscription_manager_serverurl(opts.serverurl)
                url_parts = _validate_serverurl_parsing(url_parts)
            except ValueError as e:
                # If we fail to parse, fail the conversion. The reason for
                # this harsh treatment is that we will be submitting
                # credentials to the server parsed from the serverurl. If
                # the user is specifying an internal subscription-manager
                # server but typo the url, we would fallback to the
                # public red hat subscription-manager server. That would
                # mean the user thinks the credentials are being passed
                # to their internal subscription-manager server but it
                # would really be passed externally.  That's not a good
                # security practice.
                loggerinst.critical(
                    "Failed to parse a valid subscription-manager server from the --serverurl option.\n"
                    "Please check for typos and run convert2rhel again with a corrected --serverurl.\n"
                    "Supplied serverurl: %s\nError: %s" % (opts["serverurl"], e)
                )

            rhsm_parts["rhsm_hostname"] = url_parts.hostname

            if url_parts.port:
                # urllib.parse.urlsplit() converts this into an int but we
                # always use it as a str
                rhsm_parts["rhsm_port"] = str(url_parts.port)

            if url_parts.path:
                rhsm_parts["rhsm_prefix"] = url_parts.path

        return rhsm_parts


def _parse_subscription_manager_serverurl(serverurl):
    """Parse a url string in a manner mostly compatible with subscription-manager --serverurl."""
    # This is an adaptation of what subscription-manager's cli enforces:
    # https://github.com/candlepin/subscription-manager/blob/main/src/rhsm/utils.py#L112

    # Don't modify http://<something> and https://<something> as they are fine
    if not re.match("https?://[^/]+", serverurl):
        # Anthing that looks like a malformed scheme is immediately discarded
        if re.match("^[^:]+:/.+", serverurl):
            raise ValueError("Unable to parse --serverurl. Make sure it starts with http://HOST or https://HOST")

        # If there isn't a scheme, add one now
        serverurl = "https://%s" % serverurl

    url_parts = urllib.parse.urlsplit(serverurl, allow_fragments=False)

    return url_parts


def _validate_serverurl_parsing(url_parts):
    """
    Perform some tests that we parsed the subscription-manager serverurl successfully.

    :arg url_parts: The parsed serverurl as returned by urllib.parse.urlsplit()
    :raises ValueError: If any of the checks fail.
    :returns: url_parts If the check was successful.
    """
    if url_parts.scheme not in ("https", "http"):
        raise ValueError(
            "Subscription manager must be accessed over http or https.  %s is not valid" % url_parts.scheme
        )

    if not url_parts.hostname:
        raise ValueError("A hostname must be specified in a subscription-manager serverurl")

    return url_parts


def _should_subscribe(opts):
    """
    Whether we should subscribe the system with subscription-manager.

    If there are no ways to authenticate to subscription-manager, then we will
    attempt to convert without subscribing the system.  The assumption is that
    the user has already subscribed the system or that this machine does not
    need to subscribe to rhsm in order to get the RHEL rpm packages.
    """
    # No means to authenticate with rhsm.
    if not (opts.username and opts.password) and not (opts.activation_key and opts.org):
        return False

    # --no-rhsm means that there is no need to use any part of rhsm to
    # convert this host.  (Usually used when you configure
    # your RHEL repos another way, like a local mirror and telling
    # convert2rhel about it using --enablerepo)
    if opts.no_rhsm:
        return False

    return True
