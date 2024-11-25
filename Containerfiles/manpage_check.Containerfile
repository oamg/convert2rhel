# Use the latest Fedora image as the base
FROM quay.io/fedora/fedora:latest

# Install system dependencies
RUN dnf install -y \
    python3 \
    python3-pip \
    python3-devel \
    rpm-devel \
    rpm-python \
    git \
    && dnf clean all

# Install Python packages
RUN pip3 install --upgrade pip
RUN pip3 install pexpect argparse-manpage

# Set the working directory
WORKDIR /app

# Copy the project files into the container
COPY . /app

# Copy manpage_generation.sh from the scripts directory into the container
COPY scripts/manpage_generation.sh /app/

# Ensure the script is executable
RUN chmod +x /app/manpage_generation.sh

# Set up entrypoint to run manpage_generation.sh
ENTRYPOINT ["/app/manpage_generation.sh"]
