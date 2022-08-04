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

import os
import re

from setuptools import setup

from man.build_manpage import build_manpage


# Utility function to read content of a file.
def read(fname):
    return open(os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)).read()


def get_version():
    version_source = "convert2rhel/__init__.py"
    with open(version_source) as f:
        try:
            return re.findall(
                r'^__version__ = "([^"]+)"$',
                f.read(),
                re.M,
            )[0]
        except IndexError:
            raise ValueError(
                (
                    "Unable to extract the version from %s file. Make sure the "
                    "first line has the following form: `__version__ = "
                    '"some.version.here"`'
                )
                % version_source
            )


setup(
    name="convert2rhel",
    version=get_version(),
    description="Automates the conversion of Red Hat Enterprise Linux"
    " derivative distributions to Red Hat Enterprise Linux.",
    long_description=read("README.md"),
    author="Michal Bocek",
    author_email="mbocek@redhat.com",
    url="www.redhat.com",
    license="GNU General Public License v3 or later (GPLv3+)",
    packages=["convert2rhel", "convert2rhel/pkgmanager", "convert2rhel/pkgmanager/handlers"],
    entry_points={
        "console_scripts": [
            "convert2rhel = convert2rhel.initialize:run",
        ]
    },
    cmdclass={"build_manpage": build_manpage},
    include_package_data=True,
)
