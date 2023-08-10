# -*- coding: utf-8 -*-
#
# Copyright(C) 2016 Red Hat, Inc.
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

import logging
import os
import re

from convert2rhel import backup, pkgmanager, utils
from convert2rhel.systeminfo import system_info


loggerinst = logging.getLogger(__name__)

OS_RELEASE_FILEPATH = "/etc/os-release"


def get_release_pkg_name():
    """For RHEL 7 the release package name is redhat-release-server.

    For RHEL 8, the name is redhat-release.
    """
    release_pkg_name = "redhat-release-server"

    if system_info.version.major >= 8:
        release_pkg_name = "redhat-release"

    return release_pkg_name


def get_system_release_filepath():
    """Return path of the file containing the OS name and version."""
    release_filepath = "/etc/system-release"  # RHEL 7/8 based OSes
    if os.path.isfile(release_filepath):
        return release_filepath
    loggerinst.critical("Error: Unable to find the /etc/system-release file containing the OS name and version")


def get_system_release_content():
    """Return content of the file containing name of the operating
    system and its version.
    """
    filepath = get_system_release_filepath()
    try:
        return utils.get_file_content(filepath)
    except EnvironmentError as err:
        loggerinst.critical("%s\n%s file is essential for running this tool." % (err, filepath))


class YumConf(object):
    _yum_conf_path = "/etc/yum.conf"

    def __init__(self):
        self._yum_conf_content = utils.get_file_content(self._yum_conf_path)

    def patch(self):
        """Comment out the distroverpkg variable in yum.conf so yum can determine
        release version ($releasever) based on the installed redhat-release
        package.
        """
        if YumConf.is_modified():
            # When the user touches the yum.conf before executing the conversion, then during the conversion yum as a
            # package is replaced but this config file is left unchanged and it keeps the original distroverpkg setting.
            self._comment_out_distroverpkg_tag()
            self._write_altered_yum_conf()
            loggerinst.info("%s patched." % self._yum_conf_path)
        else:
            loggerinst.info("Skipping patching, yum configuration file not modified")

        return

    def _comment_out_distroverpkg_tag(self):
        if re.search(r"^distroverpkg=", self._yum_conf_content, re.MULTILINE):
            self._yum_conf_content = re.sub(r"\n(distroverpkg=).*", r"\n#\1", self._yum_conf_content)

    def _write_altered_yum_conf(self):
        file_to_write = open(self._yum_conf_path, "w")
        try:
            file_to_write.write(self._yum_conf_content)
        finally:
            file_to_write.close()

    @staticmethod
    def get_yum_conf_filepath():
        return YumConf._yum_conf_path

    @staticmethod
    def is_modified():
        """Return true if the YUM/DNF configuration file has been modified by the user."""
        conf = "/etc/yum.conf" if pkgmanager.TYPE == "yum" else "/etc/dnf/dnf.conf"

        output, _ = utils.run_subprocess(["rpm", "-Vf", conf], print_output=False)
        # rpm -Vf does not return information about the queried file but about all files owned by the rpm
        # that owns the queried file. Character '5' on position 3 means that the file was modified.
        return True if re.search(r"^.{2}5.*? %s$" % conf, output, re.MULTILINE) else False


# Code to be executed upon module import
system_release_file = backup.RestorableFile(get_system_release_filepath())  # pylint: disable=C0103
os_release_file = backup.RestorableFile(OS_RELEASE_FILEPATH)  # pylint: disable=C0103
