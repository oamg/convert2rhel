# -*- coding: utf-8 -*-
# Copyright and permission notice compiled per:
# https://www.softwarefreedom.org/resources/2007/gpl-non-gpl-collaboration.html
#
# Copyright(C) 2018 Red Hat, Inc.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# This file incorporates work covered by the following copyright and
# permission notice:
#
#     Copyright 2016 Andi Albrecht <albrecht.andi@gmail.com>
#
#     Licensed under the Apache License, Version 2.0 (the "License")
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http: // www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#
#    The project of the original code:
#
#        https://github.com/andialbrecht/build_manpage

"""build_manpage command -- Generate man page from setup()"""

import datetime
import optparse
import re

from distutils.errors import DistutilsOptionError

from setuptools import Command


class build_manpage(Command):

    description = "Generate man page from setup()."

    user_options = [
        ("output=", "O", "output file"),
        ("parser=", None, "module path to optparser (e.g. mymod:func"),
    ]

    def initialize_options(self):
        self.output = None
        self.parser = None

    def finalize_options(self):
        if self.output is None:
            raise DistutilsOptionError("'output' option is required")
        if self.parser is None:
            raise DistutilsOptionError("'parser' option is required")

        mod_name, func_name = self.parser.split(":")

        try:
            mod = __import__(mod_name)
            self._parser = getattr(mod, func_name)()
        except ImportError:
            raise
        self._parser.formatter = ManPageFormatter()
        self._parser.formatter.set_parser(self._parser)
        self.announce("Writing man page %s" % self.output)
        self._today = datetime.date.today()

    def _markup(self, txt):
        return txt.replace("-", "\\-")

    def _write_header(self):
        version = self.distribution.get_version()
        appname = self.distribution.get_name()
        ret = []
        ret.append(
            '.TH %s 1 %s "%s v.%s"\n'
            % (
                self._markup(appname),
                self._today.strftime("%Y\\-%m\\-%d"),
                appname,
                version,
            )
        )
        description = self.distribution.get_description()
        if description:
            name = self._markup(".B %s\n.R - %s" % (self._markup(appname), description.splitlines()[0]))
        else:
            name = self._markup(appname)
        ret.append(".SH NAME\n%s\n" % name)

        synopsis = self._parser.usage
        if synopsis:
            synopsis = synopsis.replace("\n", "\n.br\n")
            synopsis = re.sub(
                r" +%s" % appname,
                ".B %s\n.R" % self._markup(appname),
                synopsis,
            )
            ret.append(".SH SYNOPSIS\n%s\n" % synopsis)
        long_desc = self.distribution.get_long_description()
        if long_desc:
            ret.append(".SH DESCRIPTION\n%s\n" % self._markup(long_desc))
        return "".join(ret)

    def _write_options(self):
        ret = [".SH OPTIONS\n"]
        ret.append(self._parser.format_option_help())
        return "".join(ret)

    def _write_footer(self):
        ret = []
        author = "%s <%s>" % (
            self.distribution.get_author(),
            self.distribution.get_author_email(),
        )
        ret.append((".SH AUTHORS\n%s" % self._markup(author)))
        # appname = self.distribution.get_name()
        # homepage = self.distribution.get_url()
        # ret.append(('.SH DISTRIBUTION\nThe latest version of %s may '
        #             'be downloaded from\n'
        #             '.UR %s\n.UE\n'
        #             % (self._markup(appname), self._markup(homepage),)))
        return "".join(ret)

    def run(self):
        manpage = []
        manpage.append(self._write_header())
        manpage.append(self._write_options())
        manpage.append(self._write_footer())
        with open(self.output, mode="w") as stream:
            stream.write("".join(manpage))


class ManPageFormatter(optparse.HelpFormatter):
    def __init__(
        self,
        indent_increment=2,
        max_help_position=24,
        width=None,
        short_first=1,
    ):
        optparse.HelpFormatter.__init__(self, indent_increment, max_help_position, width, short_first)

    def _markup(self, txt):
        return txt.replace("-", "\\-")

    def format_usage(self, usage):
        self._markup(usage)

    def format_heading(self, heading):
        if self.level == 0:
            return ""
        return ".SS\n%s\n" % self._markup(heading.upper())

    def _format_text(self, text):
        return text.strip()

    def format_option(self, option):
        result = []
        opts = self.option_strings[option]
        result.append(".TP\n.B %s\n" % self._markup(opts))
        if option.help:
            help_text = "%s\n" % self._markup(self.expand_default(option))
            result.append(help_text)
        return "".join(result)
