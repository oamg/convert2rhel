#!/bin/bash

if ! command -v podman &> /dev/null
then
    echo "Podman could not be found, installing..."
    apt-get update && apt-get install -y podman
fi

podman run --rm $(podman build -q -f Containerfiles/manpage.Containerfile)
