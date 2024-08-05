#!/usr/bin/python3

# Generate a file with convert2rhel synopsis for argparse-manpage
import os
import subprocess
import sys

from convert2rhel import toolopts


# gather the path information
manpage_script_path = os.path.abspath(__file__)

convert2rhel_path = os.path.dirname(os.path.dirname(manpage_script_path))

sys.path.append(convert2rhel_path)

# Directory to store the generated manpages
MANPAGE_DIR = "man"

print("Generating manpages")

with open(os.path.join(MANPAGE_DIR, "synopsis"), "w") as f:
    f.write("[synopsis]\n." + toolopts.CLI.usage())

# Extract the version of convert2rhel
from convert2rhel import __version__ as VER


# Generate the manpage using argparse-manpage
os.environ["PYTHONPATH"] = "."
with open(os.path.join(MANPAGE_DIR, "convert2rhel.8"), "w") as file:
    subprocess.run(
        [
            "argparse-manpage",
            "--pyfile",
            "man/__init__.py",
            "--function",
            "get_parser",
            "--manual-title",
            "General Commands Manual",
            "--description",
            "Automates the conversion of Red Hat Enterprise Linux derivative distributions to Red Hat Enterprise Linux.",
            "--project-name",
            f"convert2rhel {VER}",
            "--prog",
            "convert2rhel",
            "--include",
            "man/distribution",
            "--include",
            "man/synopsis",
        ],
        stdout=file,
        check=True,
    )

# # Check if manpages are up-to-date
# result = subprocess.run(
#     ["git", "diff", "--quiet", "HEAD", "--", os.path.join(MANPAGE_DIR, "convert2rhel.8")], check=True
# )

# if result.returncode == 0:
#     # Manpages are up-to-date, exit with 0
#     print("Manpages are up-to-date")
#     sys.exit(0)
# else:
#     # Manpages are outdated, exit with 1
#     print("Manpages are outdated")
#     sys.exit(1)
