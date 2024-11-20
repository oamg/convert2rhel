#!/bin/bash

# Directory to store the generated manpages
MANPAGE_DIR="man"

# Ensure the manpage directory exists
mkdir -p "$MANPAGE_DIR"

echo "Generating manpages"

# Generate a file with convert2rhel synopsis for argparse-manpage
python -c 'from convert2rhel import toolopts; print("[synopsis]\n."+toolopts.CLI.usage())' > "$MANPAGE_DIR/synopsis"

# Extract the current version from the spec file
CURRENT_VER=$(grep -oP '^Version:\s+\K\S+' packaging/convert2rhel.spec)
echo "Current version: $CURRENT_VER"

# Generate the manpage using argparse-manpage
PYTHONPATH=. argparse-manpage --pyfile man/__init__.py --function get_parser --manual-title="General Commands Manual" --description="Automates the conversion of Red Hat Enterprise Linux derivative distributions to Red Hat Enterprise Linux." --project-name "convert2rhel $CURRENT_VER" --prog="convert2rhel" --include man/distribution --include man/synopsis > "$MANPAGE_DIR/convert2rhel.8"


# Check for differences in the generated manpage
if ! git diff --quiet HEAD -- "$MANPAGE_DIR/convert2rhel.8"; then
    echo "Manpages are outdated. Please update them."
    exit 1
else
    echo "Manpages are up-to-date."
    exit 0
fi
