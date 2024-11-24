# Use the latest Ubuntu image as the base
FROM ubuntu:latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    rpm \
    python3-rpm \
    build-essential \
    libpopt-dev

# Install Python packages
RUN python3 -m pip install --upgrade pip
RUN pip3 install pexpect argparse-manpage

# Set the working directory
WORKDIR /app

# Copy the project files into the container
COPY . /app

# Set up entrypoint to run manpage_generation.sh
COPY manpage_generation.sh /app/
RUN chmod +x /app/manpage_generation.sh

ENTRYPOINT ["/app/manpage_generation.sh"]
