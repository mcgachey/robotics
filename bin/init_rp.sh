#!/usr/bin/env bash
# One-time (idempotent) provisioning of a bare 64-bit Raspberry Pi OS install.
# Config time only. Usage: sudo bin/init_rp.sh [branch]   (default: main)
set -euo pipefail

BRANCH=${1:-main}
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LOG=/var/log/robotics-init.log
ETC=/etc/robotics
PREFIX=/opt/robotics
DATA=/var/lib/robotics/data
NODE_HOME=/opt/node

die() { echo "ERROR: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

[ "$(id -u)" -eq 0 ] || die "run as root (sudo bin/init_rp.sh [branch])"
exec > >(tee -a "$LOG") 2>&1
echo "init_rp.sh $(date -Is) repo=$REPO branch=$BRANCH"

# 1. Preconditions
step "Checking preconditions"
[ "$(uname -m)" = "aarch64" ] || die "needs 64-bit (aarch64) OS, found $(uname -m)"
[ -e /etc/rpi-issue ] || die "this does not look like Raspberry Pi OS (no /etc/rpi-issue)"
curl -fsSI --max-time 10 https://github.com >/dev/null || die "no internet: init_rp.sh is config-time only"
git config --global --add safe.directory "$REPO"
current=$(git -C "$REPO" rev-parse --abbrev-ref HEAD)
[ "$current" = "$BRANCH" ] || die "checkout is on '$current', not '$BRANCH' (git checkout $BRANCH first)"
# shellcheck source=/dev/null
. "$REPO/deps/node.env"

# 2. Packages and swap
step "Installing apt packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git make build-essential curl ca-certificates unzip xz-utils \
  python3 python3-venv python3-pip openjdk-21-jdk-headless procps jq

step "Ensuring at least 1 GB swap"
swap_kb=$(awk '/SwapTotal/{print $2}' /proc/meminfo)
if [ "$swap_kb" -lt 1000000 ]; then
  if [ -f /etc/dphys-swapfile ]; then
    sed -i 's/^#\?CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
    grep -q '^CONF_SWAPSIZE=' /etc/dphys-swapfile || echo 'CONF_SWAPSIZE=1024' >> /etc/dphys-swapfile
    dphys-swapoff || true
    dphys-swapfile setup
    dphys-swapon
  else
    [ -f /swapfile ] || { fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile; }
    swapon /swapfile 2>/dev/null || true
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
else
  echo "swap already $((swap_kb / 1024)) MB"
fi

# 3. Node (build only)
step "Node $NODE_VERSION"
if [ "$("$NODE_HOME/bin/node" --version 2>/dev/null || true)" = "v$NODE_VERSION" ]; then
  echo "already installed"
else
  tmp=$(mktemp -d)
  tarball="node-v$NODE_VERSION-linux-arm64.tar.xz"
  curl -fsSL --max-time 600 -o "$tmp/$tarball" "https://nodejs.org/dist/v$NODE_VERSION/$tarball"
  echo "$NODE_SHA256  $tmp/$tarball" | sha256sum -c - || die "Node checksum mismatch"
  rm -rf "$NODE_HOME"; mkdir -p "$NODE_HOME"
  tar -xJf "$tmp/$tarball" -C "$NODE_HOME" --strip-components=1
  rm -rf "$tmp"
fi

# 4. User, directories, config
step "User, directories, config"
id robotics >/dev/null 2>&1 || useradd --system --home-dir "$PREFIX" --shell /usr/sbin/nologin robotics
install -d -o root -g root "$PREFIX"
install -d -o robotics -g robotics -m 750 "$DATA"
install -d -o root -g root -m 755 "$ETC"
if [ ! -f "$ETC/server.env" ]; then
  umask 077
  cat > "$ETC/server.env" <<ENV
PORT=8080
ROBOTICS_DATA_DIR=$DATA
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
BUILD_TIMEOUT_SEC=30
BUILD_MAX_HEAP_MB=256
BUILD_MAX_OUTPUT_KB=256
ENV
  umask 022
fi
chown root:root "$ETC/server.env"; chmod 600 "$ETC/server.env"

# 5. Python venv
step "Python venv"
[ -x "$PREFIX/venv/bin/python" ] || python3 -m venv "$PREFIX/venv"

# 6. systemd unit and quiet-Pi settings
step "systemd unit"
install -m 644 "$REPO/systemd/robotics.service" /etc/systemd/system/robotics.service
systemctl daemon-reload
systemctl enable robotics.service

step "Keeping the Pi quiet at classroom time"
for unit in apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service \
            unattended-upgrades.service motd-news.timer \
            systemd-networkd-wait-online.service NetworkManager-wait-online.service; do
  if systemctl list-unit-files "$unit" 2>/dev/null | grep -q "^$unit"; then
    systemctl disable --now "$unit" 2>/dev/null || systemctl disable "$unit" || true
  fi
done
cat > /etc/apt/apt.conf.d/99robotics-quiet <<'APT'
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
APT::Periodic::Download-Upgradeable-Packages "0";
APT::Periodic::AutocleanInterval "0";
APT::Get::Update::PreInvoke-Success::apt-news "";
APT
sed -i 's/^ENABLED=.*/ENABLED=0/' /etc/default/motd-news 2>/dev/null || true

# 7. Record init
step "Recording init"
printf 'REPO=%s\nBRANCH=%s\nINITIALIZED=%s\n' "$REPO" "$BRANCH" "$(date -Is)" > "$ETC/init.env"

# 8. First build and deploy
step "First build and deploy (update_rp.sh $BRANCH)"
"$REPO/bin/update_rp.sh" "$BRANCH"

# 9. First-install teacher account (lessons ship with the app; the teacher enables them)
step "Teacher account"
cd "$REPO"
if [ -e "$DATA/teacher.json" ]; then
  echo "teacher account already exists"
elif [ -t 0 ]; then
  read -r -p "Teacher username: " teacher
  make bootstrap-teacher USER="$teacher"
else
  echo "no terminal: later run  make bootstrap-teacher USER=<name>"
fi

# 10. Next steps
cat <<MSG

Provisioning complete (log: $LOG).
Offline check: disconnect the uplink, reboot, then run
  cd $REPO && sudo make check
and finish the manual steps it lists.
MSG
