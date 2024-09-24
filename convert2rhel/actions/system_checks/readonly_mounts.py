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

__metaclass__ = type


from convert2rhel import actions
from convert2rhel.logger import root_logger
from convert2rhel.utils import get_file_content


logger = root_logger.getChild(__name__)


def readonly_mount_detection(mount_point):
    """
    Mounting directly to /mnt/ is not in line with Unix FS (https://en.wikipedia.org/wiki/Unix_filesystem).
    Having /mnt/ and /sys/ read-only causes the installation of the filesystem package to
    fail (https://bugzilla.redhat.com/show_bug.cgi?id=1887513, https://github.com/oamg/convert2rhel/issues/123).
    """

    mounts = get_file_content("/proc/mounts", as_list=True)
    for line in mounts:
        _, file_mount_point, _, flags, _, _ = line.split()
        flags = flags.split(",")
        if file_mount_point == mount_point:
            if "ro" in flags:
                return True
            logger.debug("{} mount point is not read-only.".format(file_mount_point))
    logger.info("Read-only {} mount point not detected.".format(mount_point))
    return False


class ReadonlyMountMnt(actions.Action):
    id = "READ_ONLY_MOUNTS_MNT"

    def run(self):
        super(ReadonlyMountMnt, self).run()
        logger.task("Check if /mnt is read-write")

        if readonly_mount_detection("/mnt"):
            self.set_result(
                level="ERROR",
                id="MNT_DIR_READONLY_MOUNT",
                title="Read-only mount in /mnt directory",
                description=(
                    "Stopping conversion due to read-only mount to /mnt directory.\n"
                    "Mount at a subdirectory of /mnt to have /mnt writeable."
                ),
            )


class ReadonlyMountSys(actions.Action):
    id = "READ_ONLY_MOUNTS_SYS"

    def run(self):
        super(ReadonlyMountSys, self).run()
        logger.task("Check if /sys is read-write")

        if readonly_mount_detection("/sys"):
            self.set_result(
                level="ERROR",
                id="SYS_DIR_READONLY_MOUNT",
                title="Read-only mount in /sys directory",
                description=(
                    "Stopping conversion due to read-only mount to /sys directory.\n"
                    "Ensure mount point is writable before executing convert2rhel."
                ),
            )
