#!/usr/bin/env python3
"""清理测试遗留的垃圾会话（Turso + 本地 FileStore）。

在 2026-06-09 的测试隔离修复之前，test_literature_tasks.py 中的 API 测试
通过 POST /api/tasks 在真实存储中创建了大量未清理的 session。

判定规则（避免误删真实会话）：
  - 标题为默认值 "新综述"
  - 未被固定 (pinned = 0)

用法：
  backend/.venv/bin/python scripts/cleanup-test-sessions.py          # 仅预览
  backend/.venv/bin/python scripts/cleanup-test-sessions.py --force  # 实际删除
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env")


# ── 本地 FileStore 操作 ──────────────────────────────────────────────

def _list_local_sessions(data_dir: Path) -> list[dict]:
    idx_file = data_dir / "sessions" / "index.json"
    if not idx_file.is_file():
        return []
    idx = json.loads(idx_file.read_text(encoding="utf-8"))
    return idx.get("sessions") or []


def _delete_local_session(data_dir: Path, sid: str) -> bool:
    import shutil

    any_deleted = False
    for sub in ("sessions", "artifacts"):
        d = data_dir / sub / sid
        if d.is_dir():
            shutil.rmtree(d)
            any_deleted = True
    # 从 index 移除
    idx_path = data_dir / "sessions" / "index.json"
    if not idx_path.is_file():
        return any_deleted
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    before = len(idx.get("sessions") or [])
    idx["sessions"] = [s for s in (idx.get("sessions") or []) if s.get("id") != sid]
    if len(idx["sessions"]) < before:
        tmp = idx_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, idx_path)
    return True


# ── Turso 操作 ───────────────────────────────────────────────────────

def _list_turso_sessions(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT id, title, pinned, created_at, updated_at
           FROM sessions ORDER BY updated_at DESC"""
    ).fetchall()
    return [
        {"id": r[0], "title": r[1], "pinned": bool(r[2]), "created_at": r[3], "updated_at": r[4]}
        for r in rows
    ]


def _delete_turso_session(conn, sid: str) -> None:
    from app.storage.turso_repo import TursoRepo

    TursoRepo(conn=conn).delete_session(sid)


# ── 核心逻辑 ──────────────────────────────────────────────────────────

def _find_candidates(sessions: list[dict]) -> tuple[list[dict], list[str]]:
    candidates: list[dict] = []
    warnings: list[str] = []
    for s in sessions:
        sid = s["id"]
        title = s.get("title", "")
        if title != "新综述":
            continue
        if s.get("pinned", False):
            warnings.append(f"  ⚠  {sid[:16]}...  pinned=1, 跳过")
            continue
        candidates.append(s)
    return candidates, warnings


def _safe_get_connection():
    from app.storage.turso_http import get_connection

    try:
        return get_connection()
    except Exception as e:
        print(f"  [Turso] 连接失败: {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="清理测试遗留的垃圾会话")
    parser.add_argument("--force", action="store_true", help="实际删除（默认仅预览）")
    args = parser.parse_args()

    data_dir = Path(os.getenv("LITPILOT_DATA_DIR", str(ROOT / "data"))).resolve()

    # ── 收集会话 ─────────────────────────────────────────────
    conn = _safe_get_connection() if os.getenv("TURSO_DATABASE_URL") else None
    all_sessions: list[dict] = []
    seen_ids: set[str] = set()

    if conn:
        for s in _list_turso_sessions(conn):
            all_sessions.append(s)
            seen_ids.add(s["id"])
        print(f"[Turso] 共 {len(all_sessions)} 个会话")

    local_sessions = _list_local_sessions(data_dir)
    extra = [s for s in local_sessions if s["id"] not in seen_ids]
    if extra:
        all_sessions.extend(extra)
        print(f"[本地] 另有 {len(extra)} 个仅本地存在的会话")
    elif local_sessions:
        print(f"[本地] index.json 中 {len(local_sessions)} 个会话已在 Turso 中覆盖")
    else:
        print("[本地] index.json 不存在或为空")
    print(f"\n共计 {len(all_sessions)} 个会话\n")

    # ── 找出候选 ─────────────────────────────────────────────
    candidates, warnings = _find_candidates(all_sessions)

    for w in warnings:
        print(w)
    if warnings:
        print()

    if not candidates:
        print("未发现需清理的会话，一切正常。")
    else:
        print(f"发现 {len(candidates)} 个需要清理的 session：")
        for s in candidates:
            print(f"  [{s['id'][:16]}...]  "
                  f"title={s.get('title')!r}  "
                  f"created={s.get('created_at', '?')}")
        print()

        if not args.force:
            print("[DRY-RUN] 未实际删除。使用 --force 执行删除。")
        else:
            ok = fail = 0
            for s in candidates:
                sid = s["id"]
                try:
                    if conn:
                        _delete_turso_session(conn, sid)
                    if (data_dir / "sessions" / sid).is_dir():
                        _delete_local_session(data_dir, sid)
                    print(f"  ✓ {sid[:16]}...")
                    ok += 1
                except Exception as e:
                    print(f"  ✗ {sid[:16]}...: {e}")
                    fail += 1
            print(f"\n完成：成功清理 {ok} 个，失败 {fail} 个")

    if conn:
        conn.close()


if __name__ == "__main__":
    main()
