"""Lark Bitable service — multi-table aware operations via MCP.

Open/Closed: new tables are added via registry config, not code changes.
Interface Segregation: only exposes Bitable + Contact methods.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.config import get_lark_bitable_config, LarkBitableConfig
from src.models.lark_table_registry import LarkTableConfig
from src.services.mcp_client import MCPClient


@dataclass
class LarkService:
    """Multi-table Lark Bitable and Contact service."""

    config: LarkBitableConfig = field(default_factory=get_lark_bitable_config)
    _client: Optional[MCPClient] = field(default=None, init=False, repr=False)

    def __enter__(self) -> "LarkService":
        self._client = MCPClient()
        self._client.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            self._client.stop()
            self._client = None

    @property
    def client(self) -> MCPClient:
        if self._client is None:
            raise RuntimeError("LarkService must be used as context manager")
        return self._client

    # -- helpers to resolve tokens from config or LarkTableConfig ----------------

    def _resolve_token(self, app_token: Optional[str], table_cfg: Optional[LarkTableConfig] = None) -> str:
        token = app_token or (table_cfg.app_token if table_cfg else None) or self.config.app_token
        if not token:
            raise ValueError("app_token required (provide directly, via table config, or via env)")
        return token

    def _resolve_table(self, table_id: Optional[str], table_cfg: Optional[LarkTableConfig] = None) -> str:
        tid = table_id or (table_cfg.table_id if table_cfg else None) or self.config.tasks_table_id
        if not tid:
            raise ValueError("table_id required")
        return tid

    # -- App / Table management ------------------------------------------------

    def create_app(self, name: str, folder_token: Optional[str] = None) -> dict[str, Any]:
        data: dict[str, Any] = {"name": name}
        if folder_token:
            data["folder_token"] = folder_token
        return self.client.call_tool("bitable_v1_app_create", {"data": data, "useUAT": True})

    def list_tables(self, app_token: Optional[str] = None) -> list[dict[str, Any]]:
        token = self._resolve_token(app_token)
        result = self.client.call_tool("bitable_v1_appTable_list", {
            "path": {"app_token": token}, "useUAT": True,
        })
        return result.get("items", [])

    def create_table(
        self,
        name: str,
        fields: list[dict[str, Any]],
        app_token: Optional[str] = None,
        default_view_name: str = "Main View",
    ) -> dict[str, Any]:
        token = self._resolve_token(app_token)
        return self.client.call_tool("bitable_v1_appTable_create", {
            "path": {"app_token": token},
            "data": {
                "table": {
                    "name": name,
                    "default_view_name": default_view_name,
                    "fields": fields,
                }
            },
            "useUAT": True,
        })

    def list_fields(
        self,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        table_cfg: Optional[LarkTableConfig] = None,
    ) -> list[dict[str, Any]]:
        token = self._resolve_token(app_token, table_cfg)
        tid = self._resolve_table(table_id, table_cfg)
        result = self.client.call_tool("bitable_v1_appTableField_list", {
            "path": {"app_token": token, "table_id": tid}, "useUAT": True,
        })
        return result.get("items", [])

    # -- Record CRUD -----------------------------------------------------------

    def create_record(
        self,
        fields: dict[str, Any],
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        table_cfg: Optional[LarkTableConfig] = None,
    ) -> dict[str, Any]:
        token = self._resolve_token(app_token, table_cfg)
        tid = self._resolve_table(table_id, table_cfg)
        return self.client.call_tool("bitable_v1_appTableRecord_create", {
            "path": {"app_token": token, "table_id": tid},
            "data": {"fields": fields},
            "useUAT": True,
        })

    def get_record(
        self,
        record_id: str,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        table_cfg: Optional[LarkTableConfig] = None,
    ) -> dict[str, Any]:
        token = self._resolve_token(app_token, table_cfg)
        tid = self._resolve_table(table_id, table_cfg)
        return self.client.call_tool("bitable_v1_appTableRecord_get", {
            "path": {"app_token": token, "table_id": tid, "record_id": record_id},
            "useUAT": True,
        })

    def search_records(
        self,
        filter_conditions: Optional[list[dict[str, Any]]] = None,
        conjunction: str = "and",
        field_names: Optional[list[str]] = None,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        table_cfg: Optional[LarkTableConfig] = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        token = self._resolve_token(app_token, table_cfg)
        tid = self._resolve_table(table_id, table_cfg)

        data: dict[str, Any] = {}
        if filter_conditions:
            data["filter"] = {"conjunction": conjunction, "conditions": filter_conditions}
        if field_names:
            data["field_names"] = field_names

        result = self.client.call_tool("bitable_v1_appTableRecord_search", {
            "path": {"app_token": token, "table_id": tid},
            "data": data,
            "params": {"page_size": page_size},
            "useUAT": True,
        })
        return result.get("items", [])

    def update_record(
        self,
        record_id: str,
        fields: dict[str, Any],
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        table_cfg: Optional[LarkTableConfig] = None,
    ) -> dict[str, Any]:
        token = self._resolve_token(app_token, table_cfg)
        tid = self._resolve_table(table_id, table_cfg)
        return self.client.call_tool("bitable_v1_appTableRecord_update", {
            "path": {"app_token": token, "table_id": tid, "record_id": record_id},
            "data": {"fields": fields},
            "useUAT": True,
        })

    def delete_record(
        self,
        record_id: str,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        table_cfg: Optional[LarkTableConfig] = None,
    ) -> dict[str, Any]:
        token = self._resolve_token(app_token, table_cfg)
        tid = self._resolve_table(table_id, table_cfg)
        return self.client.call_tool("bitable_v1_appTableRecord_delete", {
            "path": {"app_token": token, "table_id": tid, "record_id": record_id},
            "useUAT": True,
        })

    def search_records_by_assignee(
        self,
        open_id: str,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        table_cfg: Optional[LarkTableConfig] = None,
        assignee_field: str = "Assignee",
    ) -> list[dict[str, Any]]:
        """Search records assigned to a specific Lark user."""
        return self.search_records(
            filter_conditions=[{
                "field_name": assignee_field,
                "operator": "is",
                "value": [open_id],
            }],
            app_token=app_token,
            table_id=table_id,
            table_cfg=table_cfg,
        )

    # -- Contact operations ----------------------------------------------------

    def get_user_id_by_email(self, email: str) -> Optional[str]:
        result = self.client.call_tool("contact_v3_user_batchGetId", {
            "data": {"emails": [email]},
            "params": {"user_id_type": "open_id"},
        })
        user_list = result.get("user_list", [])
        if user_list and len(user_list) > 0:
            return user_list[0].get("user_id")
        return None

    def get_user_ids_by_emails(self, emails: list[str]) -> dict[str, Optional[str]]:
        if not emails:
            return {}
        result = self.client.call_tool("contact_v3_user_batchGetId", {
            "data": {"emails": emails},
            "params": {"user_id_type": "open_id"},
        })
        mapping: dict[str, Optional[str]] = {e: None for e in emails}
        for item in result.get("user_list", []):
            email = item.get("email")
            user_id = item.get("user_id")
            if email:
                mapping[email] = user_id
        return mapping

    # -- Messaging -------------------------------------------------------------

    def send_message(
        self,
        receive_id: str,
        msg_type: str,
        content: str,
        receive_id_type: str = "chat_id",
    ) -> dict[str, Any]:
        return self.client.call_tool("im_v1_message_create", {
            "data": {
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": content,
            },
            "params": {"receive_id_type": receive_id_type},
        })

    def send_text_message(
        self, receive_id: str, text: str, receive_id_type: str = "chat_id"
    ) -> dict[str, Any]:
        content = json.dumps({"text": text})
        return self.send_message(receive_id, "text", content, receive_id_type)
