# Use the latest Ubuntu image as the base
FROM ubuntu:latest

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-venv \
    rpm \
    python3-rpm \
    build-essential \
    libpopt-dev

# Create and activate a virtual environment
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Install Python packages in the virtual environment
RUN pip install --upgrade pip
RUN pip install pexpect argparse-manpage

# Set the working directory
WORKDIR /app

# Copy the project files into the container
COPY . /app

# Set up entrypoint to run manpage_generation.sh
COPY manpage_generation.sh /app/
RUN chmod +x /app/manpage_generation.sh

ENTRYPOINT ["/app/manpage_generation.sh"]
