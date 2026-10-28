"""Copy an existing SQLite database and mask legacy free text in the copy."""
import argparse
import json
import os
import sqlite3
from pathlib import Path

from app.services.redaction import mask_text, mask_value


def migrate(source: Path, destination: Path) -> int:
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if source == destination.resolve():
        raise ValueError("目标必须是新的数据库副本")
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as old, sqlite3.connect(destination) as new:
        old.backup(new)
        tables = {row[0] for row in new.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {
            "conversation": ("title",), "message": ("content",),
            "account": ("name", "masked_number"),
            "transaction": ("counterparty", "category", "note"),
            "transferrequest": ("recipient_name", "note"),
            "pendingaction": ("details_json",),
        }
        changed = 0
        with new:
            for table, names in columns.items():
                if table not in tables:
                    continue
                available = {row[1] for row in new.execute(f'PRAGMA table_info("{table}")')}
                for name in names:
                    if name not in available:
                        continue
                    rows = new.execute(f'SELECT id, "{name}" FROM "{table}"').fetchall()
                    for identifier, value in rows:
                        if not isinstance(value, str):
                            continue
                        if name == "details_json":
                            try:
                                result = json.dumps(mask_value(json.loads(value)), ensure_ascii=False)
                            except (ValueError, TypeError):
                                raise ValueError("旧动作详情格式无效，已停止升级") from None
                        else:
                            result = mask_text(value)
                        if result != value:
                            new.execute(f'UPDATE "{table}" SET "{name}"=? WHERE id=?', (result, identifier))
                            changed += 1
        return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="在新副本中脱敏旧 SQLite 数据，保留原库")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"已生成独立副本；处理字段数：{migrate(args.source, args.destination)}")
