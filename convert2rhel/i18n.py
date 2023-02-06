# -*- coding: utf-8 -*-
#
# Copyright(C) 2021 Red Hat, Inc.
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
"""
One location to keep all locale related information.

convert2rhel is not currently localized but it does interact with other systems which are. this
module provides a single place to keep that information.  If we decide to localize convert2rhel in
the future, this file should point us towards all the locations that we may need to change.
"""

__metaclass__ = type

#
# Display locales
#

# These locales are about what we want to display to the user. If we decide to localize, these
# should be updated to retrieve the locale setting (Using the locale module from the python stdlib).
CONVERT2RHEL_LOCALE = "C"
# Subscription-manager's DBus API has its own method to set the locale. I'm not sure whether we
# would want these to obey the Display locale of the programming locale. We're likely to forward
# the error messages on to the user so display locale feels like the best fit but sometimes error
# messages are best left un-localized so that they are easier to perform a web-search for.
# We can make a decision if/when we're ready to localize convert2rhel.
SUBSCRIPTION_MANAGER_LOCALE = CONVERT2RHEL_LOCALE

#
# Programming Locale
#

# This is the locale to use for programs that we run in a subprocess and then have to interpret what
# they have done by screenscraping their output.
SCREENSCRAPED_LOCALE = "C"
