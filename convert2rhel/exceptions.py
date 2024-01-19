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

"""
This module can be used for exceptions that are used across files.  It is not necessary to use it for every exception but it is especially useful to break circular imports.
"""


class CriticalError(Exception):
    """
    Exception with the information to construct the results of an Action.

    :meth:`convert2rhel.action.Action.run` needs to set a result which will report whether the
    Action suceeded or failed and if it failed, then giving various diagnostic messages to help the
    user fix the problem. In many places, we are currently using `sys.exit()` from deep inside of the
    callstack of functions which run() calls. Those sites can be ported to use this function instead
    so that enough information is returned to make a good diagnostic message.

    .. note:: This is still not the preferred method of dealing with errors as it reverses the
        normal treatment of exceptions. This essentially gives the deepest called function the
        ability to fail the calling function. The proper way to do things is for the deepest level
        to report the error and then each caller has the opportunity to catch the exception and do
        something about it. So when we have a chance to address the technical debt, each place deep
        within the call stack should raise its own, unique exception which the callers can choose to
        catch or allow to bubble up to `Action.run`.  `Action.run` will catch any of the exceptions
        that have bubbled up and can decide what id, description, diagnosis, remediation, etc to emit.
    """

    def __init__(self, id_=None, title=None, description=None, diagnosis=None, remediation=None, variables=None):
        self.id = id_ or "MISSING_ID"
        self.title = title or "Missing title"
        self.description = description or "Missing description"
        self.diagnosis = diagnosis or ""
        self.remediation = remediation or ""
        self.variables = variables or {}

    def __repr__(self):
        return "%s(%r, %r, description=%r, diagnosis=%r, remediation=%r, variables=%r)" % (
            self.__class__.__name__,
            self.id,
            self.title,
            self.description,
            self.diagnosis,
            self.remediation,
            self.variables,
        )


class UnableToSerialize(Exception):
    """
    Internal class that is used to declare that a object was not able to be
    serialized with Pickle inside the Process subclass.
    """

    pass


class ImportGPGKeyError(Exception):
    """Raised for failures during the rpm import of gpg keys."""
