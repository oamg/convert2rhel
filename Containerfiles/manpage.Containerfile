# Use runc as the OCI runtime
# (This line is optional, as runc is the default)
# Note: If you omit this line, Podman will use runc by default
# You can also specify other runtimes (e.g., runsc, krun) if available
# See the OCI runtime documentation for details
# https://github.com/opencontainers/runtime-spec/blob/master/config.md#linux

FROM quay.io/centos/centos:stream9 as base

# Install Python and other dependencies
RUN yum install -y requirements/manpages_requirements.txt

# Set the working directory
WORKDIR /app

# Copy your Python script into the container
COPY scripts/manpage_generation.py /app/

# Make the script executable
RUN chmod +x scripts/manpage_generation.py

# Run the Python script
CMD ["/usr/bin/python3", "scripts/manpage_generation.py"]
