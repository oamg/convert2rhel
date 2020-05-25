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


def install_release_pkg():
    """Install RHEL release package, e.g. redhat-release-server."""
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Installing %s package" % get_release_pkg_name())

    SYSTEM_RELEASE_FILE.remove()
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
    """Starting with RHEL 6 the release package changed its name from
    redhat-release to redhat-release-<lowercase variant>, e.g.
    redhat-release-server.
    """
    from convert2rhel.systeminfo import system_info
    if int(system_info.version) >= 6:
        release_pkg_name = "redhat-release-" + tool_opts.variant.lower()
    else:
        release_pkg_name = "redhat-release"
    return release_pkg_name


def get_system_release_filepath():
    """Return name of the file containing name of the operating system and its
    version.
    """
    loggerinst = logging.getLogger(__name__)
    possible_release_filenames = ["system-release",  # RHEL 6/7 based OSes
                                  "oracle-release",  # Oracle Linux 5
                                  "redhat-release"]  # CentOS 5
    for release_file in possible_release_filenames:
        if os.path.isfile("/etc/%s" % release_file):
            return "/etc/%s" % release_file
    loggerinst.critical("Error: Unable to find any file containing name of the"
                        " OS and its version, e.g. /etc/system-release")


def get_system_release_content():
    """Return content of the file containing name of the operating
    system and its version.
    """
    loggerinst = logging.getLogger(__name__)
    filepath = get_system_release_filepath()
    try:
        return utils.get_file_content(filepath)
    except EnvironmentError, err:
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
SYSTEM_RELEASE_FILE = utils.RestorableFile(get_system_release_filepath())
YUM_CONF = utils.RestorableFile(YumConf.get_yum_conf_filepath())
