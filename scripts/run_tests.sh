#!/bin/bash
# Host-side unit tests for the kernel's pure algorithms.
#
# Must run from OUTSIDE the project directory: cargo config discovery walks up
# from the current directory, and the kernel's .cargo/config.toml forces
# build-std for the custom bare-metal target, which breaks the host test
# harness with duplicate lang-item errors (E0152). Running from $HOME avoids
# picking up that config.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -W)"
PROJECT="$(dirname "$SCRIPT_DIR")"
cd "$HOME"
cargo +nightly test --manifest-path "$PROJECT/tests_kernel/Cargo.toml"
