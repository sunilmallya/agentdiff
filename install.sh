#!/bin/sh
set -e

REPO="sunilmallya/agentdiff"

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

echo "agentdiff ${LATEST} (${OS_TAG}/${ARCH_TAG})"
echo ""
echo "Where do you want to install?"
echo "  1) /usr/local/bin (recommended, may need sudo)"
echo "  2) ~/.local/bin"
echo "  3) Custom path"
printf "Choice [1]: "
read -r choice

case "$choice" in
  2) INSTALL_DIR="${HOME}/.local/bin" ;;
  3) printf "Path: "; read -r INSTALL_DIR ;;
  *) INSTALL_DIR="/usr/local/bin" ;;
esac

echo "Installing to ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"

if [ -w "$INSTALL_DIR" ]; then
  curl -fsSL "$URL" -o "$INSTALL_DIR/agentdiff"
else
  sudo curl -fsSL "$URL" -o "$INSTALL_DIR/agentdiff"
fi
chmod +x "$INSTALL_DIR/agentdiff"

# Check if install dir is in PATH
case ":$PATH:" in
  *":$INSTALL_DIR:"*)
    echo "Installed: $INSTALL_DIR/agentdiff"
    ;;
  *)
    echo ""
    echo "Installed: $INSTALL_DIR/agentdiff"
    echo ""
    echo ">>> $INSTALL_DIR is not in your PATH. Run this to fix:"
    echo ""
    echo "    echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
    echo ""
    echo "    (Use ~/.bashrc instead if you use bash)"
    ;;
esac
