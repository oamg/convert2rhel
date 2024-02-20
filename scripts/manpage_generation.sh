#!/bin/bash

# Directory to store the generated manpages
MANPAGE_DIR="man"

echo Generating manpages

# Detect changes in __init__.py
if git diff --quiet HEAD~1 -- convert2rhel/__init__.py; then
    # No changes detected, exit with 0
    echo "No new version detected"
    exit 0
else
    # Changes detected, generate manpages
    # Generate a file with convert2rhel synopsis for argparse-manpage
    /usr/bin/python -c 'from convert2rhel import toolopts; print("[synopsis]\n."+toolopts.CLI.usage())' > man/synopsis

    /usr/bin/python -m pip install argparse-manpage six pexpect

    # Extract the version of convert2rhel
    VER=$(/usr/bin/python -c 'from convert2rhel import __version__; print(__version__)')

    # Generate the manpage using argparse-manpage
    PYTHONPATH=. /usr/bin/python /home/.local/bin/argparse-manpage --pyfile man/__init__.py --function get_parser --manual-title="General Commands Manual" --description="Automates the conversion of Red Hat Enterprise Linux derivative distributions to Red Hat Enterprise Linux." --project-name "convert2rhel $VER" --prog="convert2rhel" --include man/distribution --include man/synopsis > "$MANPAGE_DIR/convert2rhel.8"

    # Check if manpages are up-to-date
    if git diff --quiet HEAD -- "$MANPAGE_DIR/convert2rhel.8"; then
        # Manpages are up-to-date, exit with 0
        echo 'Manpages are up-to-date'
        exit 0
    else
        # Manpages are outdated, exit with 1
        echo 'Manpages are outdated'
        exit 1
    fi
fi
