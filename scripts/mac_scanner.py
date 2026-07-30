#!/usr/bin/env python3
"""
mac_scanner.py — Mac 本地数据扫描器
扫描 iMessage、笔记、截图/桌面文件，产出 Markdown 知识摘要。

用法：
  PYTHONPATH="$PWD" python scripts/mac_scanner.py           # 扫描并输出到 stdout
  PYTHONPATH="$PWD" python scripts/mac_scanner.py --outdir knowledge/   # 输出到知识库目录
  PYTHONPATH="$PWD" python scripts/mac_scanner.py --days 3              # 只看最近3天
"""

import sqlite3
import os
import re
import json
import argparse
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

# ── 路径常量 ──────────────────────────────────────────
HOME = Path.home()
MESSAGES_DB = HOME / "Library/Messages/chat.db"
SCREENSHOT_DIRS = [
    HOME / "Desktop",
    HOME / "Pictures",
    HOME / "Downloads",
]
NOTES_DB = HOME / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"
CACHE_DIR = HOME / ".workbuddy/scanner_cache"


# ── iMessage 扫描 ────────────────────────────────────
def scan_imessage(days: int = 7) -> list[dict]:
    """读取最近 N 天的 iMessage 记录"""
    if not MESSAGES_DB.exists():
        return [{"error": f"iMessage 数据库不存在: {MESSAGES_DB}\n  请确保已授予 终端/WorkBuddy「完全磁盘访问权限」"}]

    try:
        conn = sqlite3.connect(str(MESSAGES_DB))
        cursor = conn.cursor()
        cutoff = datetime.now() - timedelta(days=days)

        cursor.execute("""
            SELECT
                m.date / 1000000000 + strftime('%s', '2001-01-01') AS timestamp,
                m.text,
                h.id AS contact,
                m.is_from_me,
                m.cache_roomnames
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.text IS NOT NULL
              AND datetime(m.date / 1000000000 + strftime('%s', '2001-01-01'), 'unixepoch') >= ?
            ORDER BY m.date DESC
            LIMIT 200
        """, (cutoff.strftime('%Y-%m-%d %H:%M:%S'),))

        messages = []
        for row in cursor.fetchall():
            ts, text, contact, is_from_me, room = row
            direction = "发" if is_from_me == 1 else "收"
            messages.append({
                "time": datetime.fromtimestamp(ts).isoformat(),
                "direction": direction,
                "contact": contact or "未知",
                "text": text[:500] if text else "",
                "room": room,
            })
        conn.close()
        return messages
    except Exception as e:
        return [{"error": f"读取 iMessage 失败: {e}"}]


# ── Apple Notes 扫描 ─────────────────────────────────
def scan_notes(days: int = 7) -> list[dict]:
    """扫描 Apple Notes（需要完全磁盘访问权限）"""
    # Notes 数据库有多种版本，尝试常见路径
    note_dbs = [
        NOTES_DB,
        HOME / "Library/Containers/com.apple.Notes/Data/Library/Notes/NoteStore.sqlite",
    ]

    for db_path in note_dbs:
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # 新版 macOS (iOS 17+): ZICCLOUDSYNCINGOBJECT
            tables = [r[0] for r in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]

            if "ZICCLOUDSYNCINGOBJECT" in tables:
                cursor.execute("""
                    SELECT ZTITLE, ZSNIPPET, ZMODIFICATIONDATE1
                    FROM ZICCLOUDSYNCINGOBJECT
                    WHERE ZTITLE IS NOT NULL AND ZTITLE != ''
                      AND ZISPASSWORDPROTECTED IS NULL
                    ORDER BY ZMODIFICATIONDATE1 DESC
                    LIMIT 50
                """)
            elif "ZNOTE" in tables:
                cursor.execute("""
                    SELECT ZTITLE, ZSNIPPET, ZMODIFICATIONDATE
                    FROM ZNOTE
                    WHERE ZMODIFICATIONDATE IS NOT NULL
                    ORDER BY ZMODIFICATIONDATE DESC
                    LIMIT 50
                """)
            else:
                conn.close()
                continue

            notes = []
            for row in cursor.fetchall():
                title, snippet, mod_date = row
                if mod_date:
                    # Cocoa timestamp: seconds since 2001-01-01
                    ts = datetime(2001, 1, 1) + timedelta(seconds=mod_date)
                    if ts < datetime.now() - timedelta(days=days):
                        continue
                else:
                    ts = datetime.now()

                notes.append({
                    "time": ts.isoformat(),
                    "title": title or "(无标题)",
                    "snippet": (snippet or "")[:300],
                })
            conn.close()
            return notes
        except Exception as e:
            return [{"error": f"读取 Notes 失败: {e}"}]

    return [{"info": "Apple Notes 数据库未找到（可能需要完全磁盘访问权限）"}]


# ── 桌面/截图文件扫描 ────────────────────────────────
def scan_recent_files(days: int = 7) -> list[dict]:
    """扫描最近的新增/修改文件"""
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()
    results = []

    # 扫描图片文件（截图、照片）
    img_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.heif'}

    for base_dir in SCREENSHOT_DIRS:
        if not base_dir.exists():
            continue
        try:
            for f in base_dir.iterdir():
                if f.is_file() and f.stat().st_mtime > cutoff_ts:
                    ext = f.suffix.lower()
                    size_kb = f.stat().st_size / 1024

                    if ext in img_exts:
                        results.append({
                            "type": "图片",
                            "name": f.name,
                            "path": str(f),
                            "size": f"{size_kb:.0f}KB",
                            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                        })
                    elif ext in {'.md', '.txt', '.docx', '.xlsx', '.pdf', '.csv', '.json',
                                 '.yaml', '.yml', '.html', '.pptx'}:
                        results.append({
                            "type": "文档",
                            "name": f.name,
                            "path": str(f),
                            "size": f"{size_kb:.0f}KB",
                            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                        })
        except PermissionError:
            continue

    return sorted(results, key=lambda x: x["modified"], reverse=True)[:30]


# ── 知识摘要生成 ──────────────────────────────────────
def generate_summary(messages: list, notes: list, files: list, date_str: str) -> str:
    """将所有扫描结果合并为一份 Markdown 知识摘要"""
    lines = []
    lines.append(f"# 🧠 本地知识摘要 — {date_str}")
    lines.append(f"")
    lines.append(f"_由 mac_scanner.py 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    lines.append(f"")
    lines.append(f"---")

    # iMessage 摘要
    lines.append(f"")
    lines.append(f"## 💬 iMessage 对话摘要")
    lines.append(f"")
    valid_msgs = [m for m in messages if "error" not in m and "info" not in m]
    if valid_msgs:
        # 按联系人分组
        by_contact = defaultdict(list)
        for m in valid_msgs:
            by_contact[m["contact"]].append(m)

        for contact, msgs in sorted(by_contact.items()):
            send_count = sum(1 for m in msgs if m["direction"] == "发")
            recv_count = sum(1 for m in msgs if m["direction"] == "收")
            lines.append(f"### {contact} ({send_count}条发出 / {recv_count}条收到)")
            lines.append(f"")
            for m in msgs[:8]:  # 每个联系人最多8条
                direction_mark = "→" if m["direction"] == "发" else "←"
                time_short = m["time"][11:16] if len(m["time"]) > 16 else m["time"]
                text = m["text"][:200]
                lines.append(f"- {direction_mark} **{time_short}** {text}")
            if len(msgs) > 8:
                lines.append(f"  _…还有 {len(msgs)-8} 条消息_")
            lines.append(f"")
    else:
        lines.append(f"_暂无可读消息_")
        if any("error" in m for m in messages):
            lines.append(f"> ⚠️ {messages[0].get('error', '')}")
        lines.append(f"")

    # Notes 摘要
    lines.append(f"## 📝 Apple Notes 近期修改")
    lines.append(f"")
    valid_notes = [n for n in notes if "error" not in n and "info" not in n]
    if valid_notes:
        for n in valid_notes[:10]:
            time_short = n["time"][:10] if len(n["time"]) > 10 else n["time"]
            snippet = n["snippet"].replace("\n", " ")
            lines.append(f"- **{n['title']}** ({time_short}): {snippet[:150]}")
        lines.append(f"")
    else:
        lines.append(f"_暂未读取到笔记_")
        if notes and any("info" in n for n in notes):
            lines.append(f"> ℹ️ {notes[0].get('info', '')}")
        lines.append(f"")

    # 文件变动摘要
    lines.append(f"## 📁 桌面 & 下载目录文件变动")
    lines.append(f"")
    valid_files = [f for f in files if "error" not in f]
    if valid_files:
        img_files = [f for f in valid_files if f["type"] == "图片"]
        doc_files = [f for f in valid_files if f["type"] == "文档"]
        lines.append(f"- 新增/修改图片: {len(img_files)} 个")
        lines.append(f"- 新增/修改文档: {len(doc_files)} 个")
        lines.append(f"")
        if doc_files:
            lines.append(f"### 最近文档")
            for f in doc_files[:10]:
                lines.append(f"- [{f['name']}]({f['path']}) — {f['modified'][:10]} ({f['size']})")
            lines.append(f"")
    else:
        lines.append(f"_暂未扫描到文件变动_")
        lines.append(f"")

    # 元数据
    lines.append(f"---")
    lines.append(f"**元数据**:")
    lines.append(f"- 扫描范围: iMessage ({len(valid_msgs)}条) | Notes ({len(valid_notes)}条) | 文件 ({len(valid_files)}个)")
    lines.append(f"- 扫描时间: {datetime.now().isoformat()}")
    lines.append(f"- 生成器: mac_scanner.py")

    return "\n".join(lines)


# ── 主入口 ────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Mac 本地数据扫描器")
    parser.add_argument("--days", type=int, default=7, help="扫描最近几天的数据 (默认: 7)")
    parser.add_argument("--outdir", type=str, default="", help="输出目录（不指定则输出到 stdout）")
    parser.add_argument("--save-to", type=str, default="", help="保存到指定文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出原始数据")
    args = parser.parse_args()

    date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"🔍 扫描最近 {args.days} 天的本地数据...", flush=True)
    print(f"   💬 读取 iMessage...", flush=True)
    messages = scan_imessage(args.days)
    print(f"   ✅ iMessage: {len([m for m in messages if 'error' not in m])} 条消息", flush=True)
    if any("error" in m for m in messages):
        print(f"   ⚠️  {messages[0].get('error', '')}", flush=True)

    print(f"   📝 读取 Apple Notes...", flush=True)
    notes = scan_notes(args.days)
    print(f"   ✅ Notes: {len([n for n in notes if 'error' not in n and 'info' not in n])} 条笔记", flush=True)

    print(f"   📁 扫描桌面/下载文件...", flush=True)
    files = scan_recent_files(args.days)
    print(f"   ✅ 文件: {len([f for f in files if 'error' not in f])} 个", flush=True)

    if args.json:
        output = json.dumps({
            "date": date_str,
            "messages": messages,
            "notes": notes,
            "files": files,
        }, ensure_ascii=False, indent=2)
    else:
        output = generate_summary(messages, notes, files, date_str)

    # 输出
    if args.save_to:
        Path(args.save_to).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_to).write_text(output, encoding="utf-8")
        print(f"\n✅ 已保存到: {args.save_to}", flush=True)
    elif args.outdir:
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        if args.json:
            outfile = outdir / f"scanner_raw_{date_str}.json"
        else:
            outfile = outdir / f"daily_summary_{date_str}.md"
        outfile.write_text(output, encoding="utf-8")
        print(f"\n✅ 已保存到: {outfile}", flush=True)
    else:
        print("\n" + "=" * 60 + "\n")
        print(output)


if __name__ == "__main__":
    main()
