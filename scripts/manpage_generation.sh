#!/bin/bash

# Extract the current version from the spec file in the PR branch
CURRENT_VER=$(grep -oP '^Version:\s+\K\S+' packaging/convert2rhel.spec)
echo "Current version from PR: $CURRENT_VER"

# Fetch the version from the main branch
MAIN_VER=$(git show origin/main:packaging/convert2rhel.spec | grep -oP '^Version:\s+\K\S+')
echo "Version from main branch: $MAIN_VER"

# Compare versions
if [ "$CURRENT_VER" != "$MAIN_VER" ]; then
    echo "Version has changed. Please update the manpages."
    exit 1
else
    echo "Version is up-to-date."
    exit 0
fi
