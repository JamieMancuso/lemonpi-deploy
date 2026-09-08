#!/bin/bash
# Lemon Pi deploy script -- run this ON THE PI.
# Usage: bash deploy.sh [path-to-app-dir]
# Defaults to ~/lemonpi if no path given.
set -e

REPO_RAW="https://raw.githubusercontent.com/JamieMancuso/lemonpi-deploy/main"
APPDIR="${1:-$HOME/lemonpi}"

if [ ! -d "$APPDIR" ]; then
  echo "Can't find app directory: $APPDIR"
  echo "Run: bash deploy.sh /correct/path/to/lemonpi"
  exit 1
fi
cd "$APPDIR"
echo "Deploying into $APPDIR"

ts=$(date +%Y%m%d_%H%M%S)
mkdir -p "$HOME/lemonpi_backups"
tar czf "$HOME/lemonpi_backups/backup_$ts.tar.gz" theme.py widgets.py scene.py state.py page_home.py app.py assets/plant 2>/dev/null || true
echo "Backed up current app to $HOME/lemonpi_backups/backup_$ts.tar.gz"

echo "Fetching code bundle..."
curl -fsSL "$REPO_RAW/code.b64" | base64 -d > /tmp/lemonpi_code.tar.gz
echo "81e287c476a4f2b1298df615f31142e3  /tmp/lemonpi_code.tar.gz" | md5sum -c -
tar xzf /tmp/lemonpi_code.tar.gz -C "$APPDIR"
echo "Code updated."

echo "Fetching assets bundle (plant turntable images, 6 parts)..."
rm -f /tmp/lemonpi_assets.b64
for i in 1 2 3 4 5 6; do
  curl -fsSL "$REPO_RAW/assets_part${i}.b64" >> /tmp/lemonpi_assets.b64
done
base64 -d /tmp/lemonpi_assets.b64 > /tmp/lemonpi_assets.tar.gz
echo "a889a57c079848aa55186940a02e125b  /tmp/lemonpi_assets.tar.gz" | md5sum -c -
tar xzf /tmp/lemonpi_assets.tar.gz -C "$APPDIR"
echo "Assets updated."

echo "Restarting lemonpi service..."
sudo systemctl restart lemonpi
sleep 2
sudo systemctl status lemonpi --no-pager | head -n 10
echo "Done."
