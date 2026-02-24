"""
Lark Service - High-level Lark Bitable and Contact operations.

Uses src/mcp_client to communicate with the Lark MCP server.
All credentials come from environment via src/config.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.config import get_lark_bitable_config, LarkBitableConfig
from src.mcp_client import MCPClient


@dataclass
class LarkService:
    """
    Lark Bitable and Contact service.
    
    Usage:
        with LarkService() as svc:
            records = svc.search_records()
            svc.create_record({"Task Name": "New task", "Status": "To Do"})
    """
    
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
    
    # -------------------------------------------------------------------------
    # Base App Operations
    # -------------------------------------------------------------------------
    
    def create_app(self, name: str, folder_token: Optional[str] = None) -> dict[str, Any]:
        """Create a new Bitable app."""
        data: dict[str, Any] = {"name": name}
        if folder_token:
            data["folder_token"] = folder_token
        
        return self.client.call_tool("bitable_v1_app_create", {
            "data": data,
            "useUAT": True,
        })
    
    def list_tables(self, app_token: Optional[str] = None) -> list[dict[str, Any]]:
        """List all tables in a Bitable app."""
        token = app_token or self.config.app_token
        if not token:
            raise ValueError("app_token required")
        
        result = self.client.call_tool("bitable_v1_appTable_list", {
            "path": {"app_token": token},
            "useUAT": True,
        })
        return result.get("items", [])
    
    def create_table(
        self,
        name: str,
        fields: list[dict[str, Any]],
        app_token: Optional[str] = None,
        default_view_name: str = "Main View",
    ) -> dict[str, Any]:
        """
        Create a new table in a Bitable app.
        
        fields: list of field definitions, e.g.:
            [
                {"field_name": "Title", "type": 1},
                {"field_name": "Status", "type": 3, "property": {"options": [{"name": "To Do"}]}}
            ]
        
        Returns: {"table_id": "...", "field_id_list": [...], ...}
        """
        token = app_token or self.config.app_token
        if not token:
            raise ValueError("app_token required")
        
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
    ) -> list[dict[str, Any]]:
        """List all fields in a table."""
        token = app_token or self.config.app_token
        tid = table_id or self.config.tasks_table_id
        if not token or not tid:
            raise ValueError("app_token and table_id required")
        
        result = self.client.call_tool("bitable_v1_appTableField_list", {
            "path": {"app_token": token, "table_id": tid},
            "useUAT": True,
        })
        return result.get("items", [])
    
    # -------------------------------------------------------------------------
    # Record Operations
    # -------------------------------------------------------------------------
    
    def create_record(
        self,
        fields: dict[str, Any],
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Create a new record in a table.
        
        fields: dict mapping field names to values, e.g.:
            {"Task Name": "My task", "Status": "To Do"}
        
        Returns: {"record": {"record_id": "...", "fields": {...}}}
        """
        token = app_token or self.config.app_token
        tid = table_id or self.config.tasks_table_id
        if not token or not tid:
            raise ValueError("app_token and table_id required")
        
        return self.client.call_tool("bitable_v1_appTableRecord_create", {
            "path": {"app_token": token, "table_id": tid},
            "data": {"fields": fields},
            "useUAT": True,
        })
    
    def search_records(
        self,
        filter_conditions: Optional[list[dict[str, Any]]] = None,
        conjunction: str = "and",
        field_names: Optional[list[str]] = None,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search records in a table.
        
        filter_conditions: list of filter conditions, e.g.:
            [{"field_name": "Status", "operator": "is", "value": ["To Do"]}]
        
        Returns: list of records
        """
        token = app_token or self.config.app_token
        tid = table_id or self.config.tasks_table_id
        if not token or not tid:
            raise ValueError("app_token and table_id required")
        
        data: dict[str, Any] = {}
        if filter_conditions:
            data["filter"] = {
                "conjunction": conjunction,
                "conditions": filter_conditions,
            }
        if field_names:
            data["field_names"] = field_names
        
        params = {"page_size": page_size}
        
        result = self.client.call_tool("bitable_v1_appTableRecord_search", {
            "path": {"app_token": token, "table_id": tid},
            "data": data,
            "params": params,
            "useUAT": True,
        })
        return result.get("items", [])
    
    def update_record(
        self,
        record_id: str,
        fields: dict[str, Any],
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Update an existing record.
        
        fields: dict of fields to update
        
        Returns: {"record": {"record_id": "...", "fields": {...}}}
        """
        token = app_token or self.config.app_token
        tid = table_id or self.config.tasks_table_id
        if not token or not tid:
            raise ValueError("app_token and table_id required")
        
        return self.client.call_tool("bitable_v1_appTableRecord_update", {
            "path": {"app_token": token, "table_id": tid, "record_id": record_id},
            "data": {"fields": fields},
            "useUAT": True,
        })
    
    # -------------------------------------------------------------------------
    # Contact Operations
    # -------------------------------------------------------------------------
    
    def get_user_id_by_email(self, email: str) -> Optional[str]:
        """
        Resolve a user's open_id from their email address.
        
        Returns the open_id or None if not found.
        """
        result = self.client.call_tool("contact_v3_user_batchGetId", {
            "data": {"emails": [email]},
            "params": {"user_id_type": "open_id"},
        })
        
        user_list = result.get("user_list", [])
        if user_list and len(user_list) > 0:
            return user_list[0].get("user_id")
        return None
    
    def get_user_ids_by_emails(self, emails: list[str]) -> dict[str, Optional[str]]:
        """
        Resolve multiple users' open_ids from their email addresses.
        
        Returns a dict mapping email -> open_id (or None if not found).
        """
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
    
    # -------------------------------------------------------------------------
    # Messaging Operations
    # -------------------------------------------------------------------------
    
    def send_message(
        self,
        receive_id: str,
        msg_type: str,
        content: str,
        receive_id_type: str = "chat_id",
    ) -> dict[str, Any]:
        """
        Send a message to a user or chat.
        
        receive_id_type: 'open_id', 'user_id', 'email', or 'chat_id'
        msg_type: 'text', 'post', 'interactive', etc.
        content: JSON string of message content
        """
        return self.client.call_tool("im_v1_message_create", {
            "data": {
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": content,
            },
            "params": {"receive_id_type": receive_id_type},
        })
    
    def send_text_message(self, receive_id: str, text: str, receive_id_type: str = "chat_id") -> dict[str, Any]:
        """Send a simple text message."""
        import json
        content = json.dumps({"text": text})
        return self.send_message(receive_id, "text", content, receive_id_type)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------
def quick_search_records(**kwargs) -> list[dict[str, Any]]:
    """One-off search (spawns MCP server)."""
    with LarkService() as svc:
        return svc.search_records(**kwargs)


def quick_create_record(fields: dict[str, Any], **kwargs) -> dict[str, Any]:
    """One-off record creation (spawns MCP server)."""
    with LarkService() as svc:
        return svc.create_record(fields, **kwargs)


if __name__ == "__main__":
    # Quick test
    print("Testing Lark service...")
    with LarkService() as svc:
        print(f"App token: {svc.config.app_token}")
        print(f"Table ID: {svc.config.tasks_table_id}")
        
        print("\nListing fields...")
        fields = svc.list_fields()
        for f in fields:
            print(f"  - {f.get('field_name')} (type={f.get('type')})")
        
        print("\nSearching records...")
        records = svc.search_records()
        print(f"Found {len(records)} records")
