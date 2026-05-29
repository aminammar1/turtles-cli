# Use the official Python Alpine image matching the project's Python version (3.14)
FROM python:3.14-alpine

# Install build dependencies needed for Paramiko (SSH) and Cryptography compilation
# (Note: Alpine uses musl libc instead of glibc, so cargo/rust/build-base are required to compile cryptography)
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    rust \
    git \
    bash

# Copy the fast UV package manager binary into the container
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set up workspace
WORKDIR /app

# Copy dependency definition files first for optimal docker layer caching
COPY pyproject.toml uv.lock README.md /app/

# Install the dependencies globally in the system python environment
RUN uv pip install --system --no-cache -e .

# Copy the rest of the application source code
COPY . /app

# Re-install project to register any source code changes and entry points
RUN uv pip install --system --no-cache -e .

# Set default command to launch the Turtles CLI interactive shell
ENTRYPOINT ["turtle"]
