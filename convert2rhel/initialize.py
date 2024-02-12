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

__metaclass__ = type

import logging
import os

from convert2rhel import i18n
from convert2rhel import logger as logger_module


loggerinst = logging.getLogger(__name__)


def disable_root_logger():
    """
    Set the root logger to not output before dbus is imported.

    We need to initialize the root logger with the NullHandler before dbus is
    imported. Otherwise, dbus will install Handlers on the root logger which
    can end up printing our log messages an additional time.  Additionally,
    bad user data could end up causing the dbus logging to log rhsm passwords
    and other credentials.
    """
    logging.getLogger().addHandler(logging.NullHandler())


def initialize_logger():
    """
    Entrypoint function that aggregates other calls for initialization logic
    and setup for logger handlers that do not require root.
    """

    return logger_module.setup_logger_handler()


def initialize_file_logging(log_name, log_dir):
    """
    Archive existing file logs and setup all logging handlers that require
    root, like FileHandlers.

    This function should be called after
    :func:`~convert2rhel.main.initialize_logger`.

    .. warning::
        Setting log_dir underneath a world-writable directory (including
        letting it be user settable) is insecure.  We will need to write
        some checks for all calls to `os.makedirs()` if we allow changing
        log_dir.

    :param str log_name: Name of the logfile to archive and log to
    :param str log_dir: Directory where logfiles are stored
    """
    try:
        logger_module.archive_old_logger_files(log_name, log_dir)
    except (IOError, OSError) as e:
        loggerinst.warning("Unable to archive previous log: %s" % e)

    logger_module.add_file_handler(log_name, log_dir)


def set_locale():
    """
    Set the C locale, also known as the POSIX locale, for the main process as well as the child processes.

    The reason is to get predictable output from the executables we call, not
    influenced by non-default locale. We need to be setting not only LC_ALL
    and LANGUAGE but LANG as well because subscription-manager considers LANG
    to have priority over LC_ALL even though it goes against POSIX which
    specifies that LC_ALL overrides LANG.

    .. note::
        Since we introduced a new way to interact with packages that is not
        through the `yum` cli calls, but with the Python API, we had to move
        this function to a new module to initialize all the settings in
        Convert2RHEL before-hand as this was causing problems related to the
        locales. The main problem that this function solves by being here is by
        overriding any user set locale in their machine, to actually being the
        ones we require during the process execution.
    """
    os.environ.update(
        {
            "LC_ALL": i18n.SCREENSCRAPED_LOCALE,
            "LANG": i18n.SCREENSCRAPED_LOCALE,
            "LANGUAGE": i18n.SCREENSCRAPED_LOCALE,
        }
    )


def run():
    """Wrapper around the main function.

    This function is needed to initialize early code and function calls
    that have to be done before certain modules (which are imported by
    main) are imported.
    """
    # prepare environment
    set_locale()

    # Initialize logging to stop duplicate messages.
    disable_root_logger()

    # initialize logging
    initialize_logger()

    # since we now have root, we can add the FileLogging
    # and also archive previous logs
    initialize_file_logging("convert2rhel.log", logger_module.LOG_DIR)

    from convert2rhel import main

    return main.main()
