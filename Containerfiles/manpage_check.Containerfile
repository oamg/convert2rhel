# Use the latest Fedora image as the base
FROM quay.io/fedora/fedora:latest

# Install system dependencies
RUN dnf install -y \
    python3 \
    python3-pip \
    python3-devel \
    rpm-devel \
    python3-rpm \
    git \
    && dnf clean all

# Install Python packages
RUN pip3 install --upgrade pip
RUN pip3 install pexpect argparse-manpage six

# Set the working directory
WORKDIR /app

# Copy the project files into the container
COPY . /app

# Copy the convert2rhel.ini configuration file into the container
COPY config/convert2rhel.ini /etc/convert2rhel/convert2rhel.ini

# Copy manpage_generation.sh from the scripts directory into the container
COPY scripts/manpage_generation.sh /app/

# Ensure the script is executable
RUN chmod +x /app/manpage_generation.sh

# Set up entrypoint to run manpage_generation.sh
ENTRYPOINT ["/app/manpage_generation.sh"]
