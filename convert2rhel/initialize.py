# -*- coding: utf-8 -*-
#
# Copyright(C) 2022 Red Hat, Inc.
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
import sys


def set_locale():
    """Set the C locale, also known as the POSIX locale, for the main process as well as the child processes.

    The reason is to get predictable output from the executables we call, not
    influenced by non-default locale. We need to be setting not only LC_ALL but
    LANG as well because subscription-manager considers LANG to have priority
    over LC_ALL even though it goes against POSIX which specifies that LC_ALL
    overrides LANG.

    .. note::
        Since we introduced a new way to interact with packages that is not
        through the `yum` cli calls, but with the Python API, we had to move
        this function to a new module to initialize all the settings in
        Convert2RHEL before-hand as this was causing problems related to the
        locales. The main problem that this function solves by being here is by
        overriding any user set locale in their machine, to actually being the
        ones we require during the process execution.
    """
    os.environ.update({"LC_ALL": "C", "LANG": "C"})


def run():
    """Wrapper around the main function.

    This function is intended to initialize all early code and function calls
    before any other main imports.
    """
    # prepare environment
    set_locale()

    from convert2rhel import main

    sys.exit(main.main())
