#!/bin/bash

# Directory to store the generated manpages
MANPAGE_DIR="man"

VER=$(grep -oP '^Version:\s+\K\S+' packaging/convert2rhel.spec)

# Generate the manpage using argparse-manpage
PYTHONPATH=. argparse-manpage --pyfile man/__init__.py --function get_parser --manual-title="General Commands Manual" --description="Automates the conversion of Red Hat Enterprise Linux derivative distributions to Red Hat Enterprise Linux." --project-name "convert2rhle $Ver" --prog="convert2rhel" --include man/distribution --include man/synopsis > "$MANPAGE_DIR/convert2rhel.8"
