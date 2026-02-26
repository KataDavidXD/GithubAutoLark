"""Lark Bitable service — multi-table aware operations via MCP or Direct API.

Open/Closed: new tables are added via registry config, not code changes.
Interface Segregation: only exposes Bitable + Contact methods.

This service supports two modes:
1. MCP mode (default): Uses @larksuiteoapi/lark-mcp for OAuth-based operations
2. Direct API mode: Uses LarkDirectClient with auto-refreshed tenant tokens

When MCP OAuth fails (token expired), it automatically falls back to Direct API.
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
    """Multi-table Lark Bitable and Contact service.
    
    Supports both MCP and Direct API modes with automatic fallback.
    """

    config: LarkBitableConfig = field(default_factory=get_lark_bitable_config)
    use_direct_api: bool = field(default=False)  # If True, skip MCP entirely
    _client: Optional[MCPClient] = field(default=None, init=False, repr=False)
    _direct_client: Optional["LarkDirectClient"] = field(default=None, init=False, repr=False)

    def __enter__(self) -> "LarkService":
        if not self.use_direct_api:
            try:
                self._client = MCPClient()
                self._client.start()
            except Exception as e:
                print(f"[LarkService] MCP start failed, using Direct API: {e}")
                self.use_direct_api = True
        
        if self.use_direct_api:
            self._init_direct_client()
        
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._client:
            self._client.stop()
            self._client = None

    def _init_direct_client(self) -> None:
        """Initialize the direct API client lazily."""
        if self._direct_client is None:
            from src.services.lark_token_manager import LarkDirectClient
            self._direct_client = LarkDirectClient()

    @property
    def client(self) -> MCPClient:
        if self._client is None:
            raise RuntimeError("LarkService MCP client not available")
        return self._client
    
    @property
    def direct(self) -> "LarkDirectClient":
        """Get the direct API client (initializes if needed)."""
        self._init_direct_client()
        return self._direct_client  # type: ignore
    
    def _handle_mcp_auth_error(self, error: Any) -> bool:
        """Check if error is an OAuth auth error and switch to direct mode."""
        error_str = str(error)
        if "user_access_token is invalid" in error_str or "expired" in error_str:
            print("[LarkService] MCP OAuth token expired, switching to Direct API")
            self.use_direct_api = True
            self._init_direct_client()
            return True
        return False

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
        if self.use_direct_api:
            raise NotImplementedError("create_app not available in direct API mode")
        data: dict[str, Any] = {"name": name}
        if folder_token:
            data["folder_token"] = folder_token
        return self.client.call_tool("bitable_v1_app_create", {"data": data, "useUAT": True})

    def list_tables(self, app_token: Optional[str] = None) -> list[dict[str, Any]]:
        token = self._resolve_token(app_token)
        
        if self.use_direct_api:
            return self.direct.list_tables(token)
        
        try:
            result = self.client.call_tool("bitable_v1_appTable_list", {
                "path": {"app_token": token}, "useUAT": True,
            })
            # Check for auth error in response
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    return self.direct.list_tables(token)
            return result.get("items", [])
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                return self.direct.list_tables(token)
            raise

    def create_table(
        self,
        name: str,
        fields: list[dict[str, Any]],
        app_token: Optional[str] = None,
        default_view_name: str = "Grid View",
    ) -> dict[str, Any]:
        """Create a new table in a Bitable app."""
        token = self._resolve_token(app_token)
        
        if self.use_direct_api:
            self._init_direct_client()
            return self.direct.create_table(token, name, fields, default_view_name)
        
        if not self.client:
            raise RuntimeError("LarkService MCP client not available")
        
        try:
            result = self.client.call_tool("bitable_v1_appTable_create", {
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
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    return self.direct.create_table(token, name, fields, default_view_name)
            return result
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                return self.direct.create_table(token, name, fields, default_view_name)
            raise

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
        
        if self.use_direct_api:
            record = self.direct.create_record(token, tid, fields)
            return {"record": record}
        
        try:
            result = self.client.call_tool("bitable_v1_appTableRecord_create", {
                "path": {"app_token": token, "table_id": tid},
                "data": {"fields": fields},
                "useUAT": True,
            })
            # Check for auth error in response
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    record = self.direct.create_record(token, tid, fields)
                    return {"record": record}
            return result
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                record = self.direct.create_record(token, tid, fields)
                return {"record": record}
            raise

    def get_record(
        self,
        record_id: str,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        table_cfg: Optional[LarkTableConfig] = None,
    ) -> dict[str, Any]:
        token = self._resolve_token(app_token, table_cfg)
        tid = self._resolve_table(table_id, table_cfg)
        
        if self.use_direct_api:
            return self.direct.get_record(token, tid, record_id)
        
        try:
            result = self.client.call_tool("bitable_v1_appTableRecord_get", {
                "path": {"app_token": token, "table_id": tid, "record_id": record_id},
                "useUAT": True,
            })
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    return self.direct.get_record(token, tid, record_id)
            return result
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                return self.direct.get_record(token, tid, record_id)
            raise

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

        if self.use_direct_api:
            return self.direct.search_records(token, tid, filter_conditions, field_names, page_size)
        
        try:
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
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    return self.direct.search_records(token, tid, filter_conditions, field_names, page_size)
            return result.get("items", [])
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                return self.direct.search_records(token, tid, filter_conditions, field_names, page_size)
            raise

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
        
        if self.use_direct_api:
            return self.direct.update_record(token, tid, record_id, fields)
        
        try:
            result = self.client.call_tool("bitable_v1_appTableRecord_update", {
                "path": {"app_token": token, "table_id": tid, "record_id": record_id},
                "data": {"fields": fields},
                "useUAT": True,
            })
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    return self.direct.update_record(token, tid, record_id, fields)
            return result
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                return self.direct.update_record(token, tid, record_id, fields)
            raise

    def delete_record(
        self,
        record_id: str,
        app_token: Optional[str] = None,
        table_id: Optional[str] = None,
        table_cfg: Optional[LarkTableConfig] = None,
    ) -> dict[str, Any]:
        token = self._resolve_token(app_token, table_cfg)
        tid = self._resolve_table(table_id, table_cfg)
        
        if self.use_direct_api:
            self.direct.delete_record(token, tid, record_id)
            return {"deleted": True}
        
        try:
            result = self.client.call_tool("bitable_v1_appTableRecord_delete", {
                "path": {"app_token": token, "table_id": tid, "record_id": record_id},
                "useUAT": True,
            })
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    self.direct.delete_record(token, tid, record_id)
                    return {"deleted": True}
            return result
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                self.direct.delete_record(token, tid, record_id)
                return {"deleted": True}
            raise

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
        if self.use_direct_api:
            user = self.direct.get_user_by_email(email)
            return user.get("user_id") if user else None
        
        try:
            result = self.client.call_tool("contact_v3_user_batchGetId", {
                "data": {"emails": [email]},
                "params": {"user_id_type": "open_id"},
            })
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    user = self.direct.get_user_by_email(email)
                    return user.get("user_id") if user else None
            user_list = result.get("user_list", [])
            if user_list and len(user_list) > 0:
                return user_list[0].get("user_id")
            return None
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                user = self.direct.get_user_by_email(email)
                return user.get("user_id") if user else None
            raise

    def get_user_ids_by_emails(self, emails: list[str]) -> dict[str, Optional[str]]:
        if not emails:
            return {}
        
        if self.use_direct_api:
            return self.direct.get_users_by_emails(emails)
        
        try:
            result = self.client.call_tool("contact_v3_user_batchGetId", {
                "data": {"emails": emails},
                "params": {"user_id_type": "open_id"},
            })
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    return self.direct.get_users_by_emails(emails)
            mapping: dict[str, Optional[str]] = {e: None for e in emails}
            for item in result.get("user_list", []):
                email = item.get("email")
                user_id = item.get("user_id")
                if email:
                    mapping[email] = user_id
            return mapping
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                return self.direct.get_users_by_emails(emails)
            raise

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

    # -- Organization / Department operations ----------------------------------

    def list_organization_users(self, department_id: str = "0") -> list[dict[str, Any]]:
        """List all users in the Lark organization.
        
        Args:
            department_id: Department ID ("0" for root = all users)
        """
        if self.use_direct_api:
            return self.direct.list_department_users(department_id)
        
        try:
            result = self.client.call_tool("contact_v3_user_list", {
                "params": {
                    "department_id": department_id,
                    "page_size": 50,
                    "user_id_type": "open_id",
                },
            })
            if isinstance(result, dict) and "errorMessage" in result:
                if self._handle_mcp_auth_error(result.get("errorMessage", "")):
                    return self.direct.list_department_users(department_id)
            return result.get("items", [])
        except Exception as e:
            if self._handle_mcp_auth_error(e):
                return self.direct.list_department_users(department_id)
            raise

    # -- Document Permission operations ----------------------------------------

    def transfer_bitable_owner(
        self,
        new_owner_id: str,
        app_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Transfer Bitable ownership to another user.
        
        Args:
            new_owner_id: The open_id of the new owner
            app_token: Optional app token (defaults to configured one)
        """
        token = self._resolve_token(app_token)
        return self.direct.transfer_bitable_owner(token, new_owner_id)

    def add_bitable_collaborator(
        self,
        member_id: str,
        perm: str = "full_access",
        app_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Add a collaborator to a Bitable document.
        
        Args:
            member_id: The open_id of the user to add
            perm: Permission level ("view", "edit", "full_access")
            app_token: Optional app token
        """
        token = self._resolve_token(app_token)
        return self.direct.add_bitable_collaborator(token, member_id, perm=perm)

    def list_bitable_collaborators(self, app_token: Optional[str] = None) -> list[dict[str, Any]]:
        """List all collaborators of a Bitable document."""
        token = self._resolve_token(app_token)
        return self.direct.list_bitable_collaborators(token)
