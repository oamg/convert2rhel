#!/bin/bash

# Define the installation directory
INSTALL_DIR="$HOME/.local/bin"

# Create the directory if it doesn't exist
mkdir -p $INSTALL_DIR

# Add the installation directory to PATH
export PATH=$INSTALL_DIR:$PATH

# Check if podman is installed
if ! command -v podman &> /dev/null
then
    echo "Podman could not be found, installing..."
    # Download and install podman from an alternative URL
    curl -L https://download.copr.fedorainfracloud.org/results/@podman/stable/epel-7-x86_64/podman-remote-static.tar.gz | tar -xz -C $INSTALL_DIR
fi

# Run the container
podman run --rm $(podman build -q -f Containerfiles/manpage.Containerfile)
