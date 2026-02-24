#!/usr/bin/env python3
"""Initialize the database and optionally seed with data from YAML files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.lark_table_repo import LarkTableRepository
from src.models.member import Member, MemberRole
from src.models.lark_table_registry import LarkTableConfig


def main():
    parser = argparse.ArgumentParser(description="Initialize the database")
    parser.add_argument("--seed-members", type=str, help="YAML file with member definitions")
    parser.add_argument("--seed-tables", type=str, help="YAML file with table definitions")
    parser.add_argument("--db-path", type=str, help="Override database path")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else None
    db = Database(path=db_path)
    db.init()
    print(f"Database initialized at: {db.path}")

    if args.seed_members:
        _seed_members(db, Path(args.seed_members))

    if args.seed_tables:
        _seed_tables(db, Path(args.seed_tables))

    db.close()
    print("Done.")


def _seed_members(db: Database, path: Path):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    repo = MemberRepository(db)
    for m in data.get("members", []):
        try:
            member = Member(
                name=m["name"],
                email=m["email"],
                role=MemberRole(m.get("role", "member")),
                github_username=m.get("github_username"),
                position=m.get("position"),
                team=m.get("team"),
            )
            repo.create(member)
            print(f"  Created member: {member.name} ({member.email})")
        except Exception as e:
            print(f"  Skipping {m.get('name', '?')}: {e}")


def _seed_tables(db: Database, path: Path):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    repo = LarkTableRepository(db)
    for t in data.get("tables", []):
        try:
            cfg = LarkTableConfig(
                app_token=t["app_token"],
                table_id=t["table_id"],
                table_name=t["table_name"],
                description=t.get("description"),
                field_mapping=t.get("field_mapping", {}),
                is_default=t.get("is_default", False),
            )
            repo.register(cfg)
            print(f"  Registered table: {cfg.table_name}")
        except Exception as e:
            print(f"  Skipping {t.get('table_name', '?')}: {e}")


if __name__ == "__main__":
    main()
