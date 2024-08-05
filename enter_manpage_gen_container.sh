#!/bin/bash

if ! command -v podman &> /dev/null
then
    echo "Podman could not be found, installing..."
    yum install -y podman
fi

podman run --rm $(podman build -q -f Containerfiles/manpage.Containerfile)
