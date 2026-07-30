#!/bin/bash
# sync_sentient_to_nas.sh — 将 SentientOS 产出同步到 NAS 知识库
# 由 cron / launchd / GitHub Actions 定时触发

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/../config/local.yaml"
NAS_MOUNT="/Volumes/NAS"
SENTIENT_OUTPUT="$HOME/SentientOS/glow"
KB_PATH="$NAS_MOUNT/sentient-nas-bridge/knowledge"
LOG_FILE="$SCRIPT_DIR/../logs/sync_$(date +%Y%m%d_%H%M%S).log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# 检查 NAS 是否挂载
check_nas() {
    if [ ! -d "$NAS_MOUNT" ]; then
        log "ERROR: NAS not mounted at $NAS_MOUNT"
        return 1
    fi
    return 0
}

# 确保知识库目录存在
ensure_dir() {
    mkdir -p "$KB_PATH" "$(dirname "$LOG_FILE")"
}

# 同步：SentientOS → NAS
sync_to_nas() {
    log "Syncing SentientOS output → NAS..."
    
    if [ ! -d "$SENTIENT_OUTPUT" ]; then
        log "WARN: SentientOS output dir not found: $SENTIENT_OUTPUT"
        return 1
    fi
    
    # rsync 增量同步
    rsync -avz --delete \
        --include="*.md" \
        --include="*.json" \
        --include="*.yaml" \
        --exclude="*" \
        "$SENTIENT_OUTPUT/" "$KB_PATH/sentient_data/"
    
    log "Sync complete: $(find "$KB_PATH/sentient_data" -type f | wc -l) files"
}

# 生成增量摘要（供 WorkBuddy 读取）
generate_summary() {
    local summary_file="$KB_PATH/daily_summary_$(date +%Y-%m-%d).md"
    
    echo "# SentientOS Daily Summary — $(date +%Y-%m-%d)" > "$summary_file"
    echo "" >> "$summary_file"
    
    # 统计新文件
    find "$KB_PATH/sentient_data" -mtime -1 -type f | while read -r f; do
        echo "- [$(basename "$f")]($f)"
    done >> "$summary_file"
    
    log "Summary generated: $summary_file"
}

main() {
    log "=== Sentient → NAS Sync Started ==="
    
    ensure_dir
    
    if check_nas; then
        sync_to_nas
        generate_summary
        log "=== Sync successful ==="
    else
        log "=== Sync failed: NAS not available ==="
        exit 1
    fi
}

main
