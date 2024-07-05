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

import errno
import logging
import os
import shutil

from convert2rhel import actions
from convert2rhel.utils import TMP_DIR


loggerinst = logging.getLogger(__name__)


class RemoveTmpDir(actions.Action):
    id = "REMOVE_TMP_DIR"
    dependencies = ()
    tmp_dir = TMP_DIR

    def run(self):
        """Remove the temporary directory (used for backups) and its
        contents (if any) after the conversion is done. Warns if the
        removal fails.

        This function is idempotent and will do nothing if the
        temporary directory does not exist.
        """
        super(RemoveTmpDir, self).run()
        try:
            shutil.rmtree(self.tmp_dir)
            loggerinst.info("Temporary folder %s removed" % self.tmp_dir)
        except OSError as exc:
            # We want run() to be idempotent, so do nothing silently if
            # the path doesn't exist.
            # In Python 3 this could be changed to FileNotFoundError.
            if exc.errno == errno.ENOENT:
                return
            warning_message = (
                "The folder %s is left untouched. You may remove the folder manually"
                " after you ensure there is no preserved data you would need." % self.tmp_dir
            )
            loggerinst.warning(warning_message)
