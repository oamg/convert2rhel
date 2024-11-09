#!/bin/bash

# Directory to store the generated manpages
MANPAGE_DIR="man"

# Extract the current version from the spec file in the PR branch
CURRENT_VER=$(grep -oP '^Version:\s+\K\S+' packaging/convert2rhel.spec)
echo "Current version from PR: $CURRENT_VER"

# Fetch the version from the main branch
MAIN_VER=$(git show origin/main:packaging/convert2rhel.spec | grep -oP '^Version:\s+\K\S+')
echo "Version from main branch: $MAIN_VER"

# Compare versions
if [ "$CURRENT_VER" != "$MAIN_VER" ]; then
    echo "Version has changed. Please update the manpages."

   # Generate a file with convert2rhel synopsis for argparse-manpage
    python -c 'from convert2rhel import toolopts; print("[synopsis]\n."+toolopts.CLI.usage())' > man/synopsis

    # Generate the manpage using argparse-manpage
    PYTHONPATH=. argparse-manpage --pyfile man/__init__.py --function get_parser --manual-title="General Commands Manual" --description="Automates the conversion of Red Hat Enterprise Linux derivative distributions to Red Hat Enterprise Linux." --project-name "convert2rhel $VER" --prog="convert2rhel" --include man/distribution --include man/synopsis > "$MANPAGE_DIR/convert2rhel.8"

    # Check for differences in the generated manpage
    if ! git diff --quiet HEAD -- "$MANPAGE_DIR/convert2rhel.8"; then
        echo "Manpages are outdated. Please update them."
        exit 1
    else
        echo "Manpages are up-to-date."
        exit 0
    fi
else
    echo "Version is up-to-date."
    exit 0
fi
