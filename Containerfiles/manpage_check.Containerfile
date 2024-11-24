# Use the latest Ubuntu image as the base
FROM ubuntu:latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-venv \
    rpm \
    librpm-dev \
    build-essential \
    libpopt-dev \
    git

# Create and activate a virtual environment
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Install Python packages in the virtual environment
RUN pip install --upgrade pip
RUN pip install pexpect argparse-manpage

# Install rpm-python bindings using pip within the virtual environment
RUN pip install rpm-py-installer
RUN rpm_py_installer --install-latest

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
