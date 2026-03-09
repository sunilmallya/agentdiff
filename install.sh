#!/bin/sh
set -e

REPO="sunilmallya/agentdiff"
INSTALL_DIR="/usr/local/bin"

# Detect OS and architecture
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Darwin) OS_TAG="darwin" ;;
  Linux)  OS_TAG="linux" ;;
  *)      echo "Unsupported OS: $OS"; exit 1 ;;
esac

case "$ARCH" in
  arm64|aarch64) ARCH_TAG="arm64" ;;
  x86_64)        ARCH_TAG="x86_64" ;;
  *)             echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

BINARY="agentdiff-${OS_TAG}-${ARCH_TAG}"

# Get latest release tag
LATEST=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" | grep '"tag_name"' | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')

if [ -z "$LATEST" ]; then
  echo "Error: could not determine latest release"
  exit 1
fi

URL="https://github.com/${REPO}/releases/download/${LATEST}/${BINARY}"

echo "Installing agentdiff ${LATEST} (${OS_TAG}/${ARCH_TAG})..."

curl -fsSL "$URL" -o /tmp/agentdiff
chmod +x /tmp/agentdiff

if [ -w "$INSTALL_DIR" ]; then
  mv /tmp/agentdiff "$INSTALL_DIR/agentdiff"
else
  echo "Need sudo to install to ${INSTALL_DIR}"
  sudo mv /tmp/agentdiff "$INSTALL_DIR/agentdiff"
fi

echo "Installed: $(agentdiff --version)"
