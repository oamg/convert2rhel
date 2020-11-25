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

import glob
import logging
import os
from re import sub

from convert2rhel import utils
from convert2rhel.toolopts import tool_opts
from convert2rhel.systeminfo import system_info


def install_release_pkg():
    """Install RHEL release package, e.g. redhat-release-server."""
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Installing %s package" % get_release_pkg_name())

    system_release_file.remove()
    pkg_path = os.path.join(utils.DATA_DIR, "redhat-release",
                            tool_opts.variant, "redhat-release-*")

    success = utils.install_pkgs(glob.glob(pkg_path))
    if success:
        loggerinst.info("Release package successfully installed.")

    # installing rhel6.x release package also installs
    # /etc/yum.repos.d/rhel-source.repo which may cause user issue when running
    # tool with --disable-submgr and custom repos therefore it is recommended
    # to remove this file so it does not impact the next steps this is only
    # done when user selects to disable submgr
    repofile = "/etc/yum.repos.d/rhel-source.repo"
    if tool_opts.disable_submgr and os.path.isfile(repofile):
        loggerinst.info("Removing /etc/yum.repos.d/rhel-source.repo "
                        "that was installed by the package ...")
        os.remove(repofile)
    return


def get_release_pkg_name():
    """For RHEL 6 and 7 the release package name follows this schema: redhat-release-<lowercase variant>, e.g.
    redhat-release-server.

    For RHEL 8, the name is just redhat-release.
    """
    if system_info.version in ["6", "7"]:
        return "redhat-release-" + tool_opts.variant.lower()
    elif system_info.version == "8":
        return "redhat-release"


def get_system_release_filepath():
    """Return path of the file containing the OS name and version."""
    release_filepath = "/etc/system-release"  # RHEL 6/7/8 based OSes
    if os.path.isfile(release_filepath):
        return release_filepath
    loggerinst = logging.getLogger(__name__)
    loggerinst.critical("Error: Unable to find the /etc/system-release file containing the OS name and version")


def get_system_release_content():
    """Return content of the file containing name of the operating
    system and its version.
    """
    loggerinst = logging.getLogger(__name__)
    filepath = get_system_release_filepath()
    try:
        return utils.get_file_content(filepath)
    except EnvironmentError as err:
        loggerinst.critical("%s\n%s file is essential for running this tool."
                            % (err, filepath))


class YumConf(object):
    _yum_conf_path = "/etc/yum.conf"

    def __init__(self):
        self._yum_conf_content = utils.get_file_content(self._yum_conf_path)
        self.loggerinst = logging.getLogger(__name__)

    def patch(self):
        """Replace distroverpkg variable in yum.conf so yum can determine
        release version ($releasever) based on the installed redhat-release
        package.
        """
        self._insert_distroverpkg_tag()
        self._write_altered_yum_conf()
        self.loggerinst.debug("%s patched." % self._yum_conf_path)
        return

    def _insert_distroverpkg_tag(self):
        if "distroverpkg=" not in self._yum_conf_content:
            self._yum_conf_content = sub(
                r"(\[main\].*)", r"\1\ndistroverpkg=%s" %
                get_release_pkg_name(),
                self._yum_conf_content)
        else:
            self._yum_conf_content = sub(
                r"(distroverpkg=).*",
                r"\1%s" % get_release_pkg_name(),
                self._yum_conf_content)

    def _write_altered_yum_conf(self):
        file_to_write = open(self._yum_conf_path, 'w')
        try:
            file_to_write.write(self._yum_conf_content)
        finally:
            file_to_write.close()

    @staticmethod
    def get_yum_conf_filepath():
        return YumConf._yum_conf_path


# Code to be executed upon module import
system_release_file = utils.RestorableFile(get_system_release_filepath())  # pylint: disable=C0103
yum_conf = utils.RestorableFile(YumConf.get_yum_conf_filepath())  # pylint: disable=C0103
