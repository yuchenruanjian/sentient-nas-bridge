#!/bin/bash
# mount_nas.sh — 挂载 NAS 卷到本地
# 首次使用前：brew install osxfuse && brew install sshfs（如果用 SSHFS）
# 或使用系统原生 SMB 挂载

set -euo pipefail

NAS_IP="${NAS_IP:-192.168.1.100}"
NAS_SHARE="${NAS_SHARE:-knowledge}"
NAS_USER="${NAS_USER:-}"
NAS_PASS="${NAS_PASS:-}"
MOUNT_POINT="/Volumes/NAS"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# 检查是否已挂载
if mount | grep -q "on $MOUNT_POINT "; then
    log "NAS already mounted at $MOUNT_POINT"
    exit 0
fi

# 确保挂载点存在
sudo mkdir -p "$MOUNT_POINT"

log "Mounting NAS at $MOUNT_POINT..."

if [ -n "$NAS_USER" ] && [ -n "$NAS_PASS" ]; then
    # SMB 挂载（Synology / QNAP 通用）
    mount_smbfs "//${NAS_USER}:${NAS_PASS}@${NAS_IP}/${NAS_SHARE}" "$MOUNT_POINT"
else
    # 无密码挂载（访客模式）
    mount_smbfs "//guest@${NAS_IP}/${NAS_SHARE}" "$MOUNT_POINT"
fi

log "NAS mounted successfully"
echo "NAS_SHARE=${NAS_SHARE}" > "$HOME/.nas_env"
