# Docksmith

Docksmith is a simplified, lightweight Docker-like build and runtime container system built entirely in Python. It allows you to build container images from a `Docksmithfile` (similar to a Dockerfile), manage a local cache of image layers deterministically, and run isolated containerized processes.

## Features

- **Image Building (`Docksmithfile`)**: Supports `FROM`, `WORKDIR`, `ENV`, `COPY`, `RUN`, and `CMD` instructions.
- **Layered Architecture & Content-Addressable Storage**: Images are built using deterministic delta layers (tarballs) stored by their SHA-256 digest, mimicking union filesystems.
- **Aggressive Caching**: Fast rebuilds! Reuses layers based on precise cache key computations (parent layer, instruction, environment, file hashes).
- **Process Isolation**: Containers run isolated using Linux `chroot` and `sudo` entirely detached from the host's filesystem space.
- **Image Management**: Tools to import, list (`images`), and remove (`rmi`) built images.

## Project Structure

```text
docksmith/
├── builder.py    # Orchestrates parsing, executing steps, caching, and manifest creation
├── cache.py      # Computes cache keys for deterministic rebuilds
├── image.py      # Creates and manages image JSON manifests
├── importer.py   # Imports raw rootfs tarballs as base images
├── isolate.py    # Sandboxes container runtime processes using `chroot`
├── layers.py     # Deterministic file archiving and layer delta extraction
├── parser.py     # Parses and validates `Docksmithfile` syntax
├── runtime.py    # Container runner environment setup (layers extraction & execution)
└── state.py      # Manages the ~/.docksmith local filesystem structure
main.py           # CLI entrypoint
```

## Prerequisites

- Python 3.10+
- A Linux environment (or WSL on Windows) - **Note:** Docksmith relies on `chroot` and `sudo` for container isolation, which are native to Linux.

## Installation

Add `main.py` to your path or run it directly:

```bash
pip install -r requirements.txt # if any dependencies exist
chmod +x main.py
alias docksmith="./main.py"
```

## Usage

### 1. Import a base image
Before building, you need a base OS layer (like Alpine Linux). You can download an Alpine minirootfs tarball and import it:
```bash
docksmith import alpine-minirootfs-3.18.0-x86_64.tar.gz alpine 3.18
```

### 2. Create a `Docksmithfile`
Create a folder `myapp/` with a `Docksmithfile`:
```dockerfile
FROM alpine:3.18
WORKDIR /app
ENV APP_ENV=production
COPY app.py /app/
RUN echo "Setting up application..." > setup.log
CMD ["python3", "app.py"]
```

### 3. Build an image
```bash
docksmith build -t myapp:latest ./myapp
```
*Note: Add `--no-cache` to force rebuild all layers.*

### 4. List Images
```bash
docksmith images
```

### 5. Run a Container
```bash
docksmith run myapp:latest
```
*You can override environment variables or the default command:*
```bash
docksmith run -e APP_ENV=development myapp:latest
```

### 6. Remove an Image
```bash
docksmith rmi myapp:latest
```

## How It Works

1. **State Directory**: Docksmith stores everything under `~/.docksmith/` (JSON manifests in `/images/`, `.tar` layer blobs in `/layers/`, and `index.json` in `/cache/`).
2. **Caching**: The cache key for `COPY` and `RUN` is a SHA-256 hash of the parent layer digest, instruction text, current working directory, environment variables, and (for COPY) the source file hashes. If inputs don't change, steps complete in milliseconds.
3. **Layers**: Each `RUN` command is executed inside a temporary `chroot` environment created by extracting previous layers. A snapshot is taken before and after execution to calculate delta file changes.
4. **Isolation**: When `docksmith run` is executed, the entire image layer stack is extracted into a temporary directory. The `isolate.py` module executes `sudo chroot` to restrict the process runtime strictly to the extracted filesystem.
