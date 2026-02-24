"""Repository for the ``lark_tables_registry`` table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.db.database import Database
from src.models.lark_table_registry import LarkTableConfig


class LarkTableRepository:
    """Single-Responsibility repository for Lark table registry."""

    def __init__(self, db: Database):
        self._db = db

    # -- Create ----------------------------------------------------------------

    def register(self, config: LarkTableConfig) -> LarkTableConfig:
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO lark_tables_registry
                   (registry_id, app_token, table_id, table_name,
                    description, field_mapping, is_default)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    config.registry_id, config.app_token, config.table_id,
                    config.table_name, config.description,
                    config.field_mapping_json(), 1 if config.is_default else 0,
                ),
            )
        return config

    # -- Read ------------------------------------------------------------------

    def get_by_id(self, registry_id: str) -> Optional[LarkTableConfig]:
        row = self._db.fetchone(
            "SELECT * FROM lark_tables_registry WHERE registry_id = ?", (registry_id,)
        )
        return LarkTableConfig.from_row(row) if row else None

    def get_by_table_id(self, app_token: str, table_id: str) -> Optional[LarkTableConfig]:
        row = self._db.fetchone(
            "SELECT * FROM lark_tables_registry WHERE app_token = ? AND table_id = ?",
            (app_token, table_id),
        )
        return LarkTableConfig.from_row(row) if row else None

    def get_by_name(self, table_name: str) -> Optional[LarkTableConfig]:
        row = self._db.fetchone(
            "SELECT * FROM lark_tables_registry WHERE LOWER(table_name) = ?",
            (table_name.lower(),),
        )
        return LarkTableConfig.from_row(row) if row else None

    def get_default(self) -> Optional[LarkTableConfig]:
        row = self._db.fetchone(
            "SELECT * FROM lark_tables_registry WHERE is_default = 1 LIMIT 1"
        )
        return LarkTableConfig.from_row(row) if row else None

    def list_all(self) -> list[LarkTableConfig]:
        rows = self._db.fetchall(
            "SELECT * FROM lark_tables_registry ORDER BY table_name"
        )
        return [LarkTableConfig.from_row(r) for r in rows]

    # -- Update ----------------------------------------------------------------

    def update(self, registry_id: str, **fields: Any) -> Optional[LarkTableConfig]:
        if not fields:
            return self.get_by_id(registry_id)

        allowed = {"table_name", "description", "field_mapping", "is_default"}
        filtered = {k: v for k, v in fields.items() if k in allowed}
        if not filtered:
            return self.get_by_id(registry_id)

        set_parts = [f"{k} = ?" for k in filtered]
        set_parts.append("updated_at = ?")
        values = list(filtered.values())
        values.append(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        values.append(registry_id)

        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE lark_tables_registry SET {', '.join(set_parts)} WHERE registry_id = ?",
                tuple(values),
            )
        return self.get_by_id(registry_id)

    def set_default(self, registry_id: str) -> None:
        """Mark one table as default (unset all others first)."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE lark_tables_registry SET is_default = 0, updated_at = ?",
                (now,),
            )
            conn.execute(
                "UPDATE lark_tables_registry SET is_default = 1, updated_at = ? WHERE registry_id = ?",
                (now, registry_id),
            )

    # -- Delete ----------------------------------------------------------------

    def delete(self, registry_id: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM lark_tables_registry WHERE registry_id = ?", (registry_id,)
            )
        return cursor.rowcount > 0
