"""Lark Token Manager — Automatic token acquisition and refresh.

This module handles the OAuth token lifecycle for Lark API:
1. Tenant Access Token (TAT) - App-level token, auto-refreshed
2. User Access Token (UAT) - User-level token with refresh_token support

For automated agent systems, TAT is preferred as it requires no user interaction.
UAT is used when user-specific operations are needed.
"""

from __future__ import annotations

import json
import os
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

from src.config import get_lark_mcp_config, get_repo_root


@dataclass
class TokenInfo:
    """Stores token with expiration metadata."""
    token: str
    token_type: str  # "tenant" or "user"
    expires_at: float  # Unix timestamp
    refresh_token: Optional[str] = None  # Only for user tokens
    
    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if token is expired or will expire within buffer."""
        return time.time() >= (self.expires_at - buffer_seconds)
    
    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "refresh_token": self.refresh_token,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TokenInfo":
        return cls(
            token=data["token"],
            token_type=data["token_type"],
            expires_at=data["expires_at"],
            refresh_token=data.get("refresh_token"),
        )


class LarkTokenManager:
    """Manages Lark API tokens with automatic refresh.
    
    Usage:
        manager = LarkTokenManager()
        
        # Get tenant token (auto-refreshes if needed)
        tat = manager.get_tenant_access_token()
        
        # Get user token (requires initial authorization)
        uat = manager.get_user_access_token()
    """
    
    TOKEN_FILE = "data/.lark_tokens.json"
    
    # Lark API endpoints
    TENANT_TOKEN_URL = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    APP_TOKEN_URL = "https://open.larksuite.com/open-apis/auth/v3/app_access_token/internal"
    USER_TOKEN_URL = "https://open.larksuite.com/open-apis/authen/v1/oidc/access_token"
    REFRESH_TOKEN_URL = "https://open.larksuite.com/open-apis/authen/v1/oidc/refresh_access_token"
    
    def __init__(self, config=None):
        self.config = config or get_lark_mcp_config()
        self._lock = threading.Lock()
        self._tokens: dict[str, TokenInfo] = {}
        self._token_file = get_repo_root() / self.TOKEN_FILE
        self._load_tokens()
    
    # =========================================================================
    # Token Persistence
    # =========================================================================
    
    def _load_tokens(self) -> None:
        """Load tokens from persistent storage."""
        if self._token_file.exists():
            try:
                with open(self._token_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, token_data in data.items():
                        self._tokens[key] = TokenInfo.from_dict(token_data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[TokenManager] Warning: Could not load tokens: {e}")
                self._tokens = {}
    
    def _save_tokens(self) -> None:
        """Save tokens to persistent storage."""
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        data = {key: token.to_dict() for key, token in self._tokens.items()}
        with open(self._token_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    # =========================================================================
    # Tenant Access Token (No user interaction required)
    # =========================================================================
    
    def get_tenant_access_token(self, force_refresh: bool = False) -> str:
        """Get tenant access token, refreshing if needed.
        
        This token is used for app-level operations and can be
        obtained automatically without user interaction.
        
        Returns:
            The tenant access token string
            
        Raises:
            RuntimeError: If token cannot be obtained
        """
        with self._lock:
            token_key = "tenant"
            
            if not force_refresh and token_key in self._tokens:
                token_info = self._tokens[token_key]
                if not token_info.is_expired():
                    return token_info.token
            
            # Refresh the token
            token_info = self._fetch_tenant_access_token()
            self._tokens[token_key] = token_info
            self._save_tokens()
            return token_info.token
    
    def _fetch_tenant_access_token(self) -> TokenInfo:
        """Fetch a new tenant access token from Lark API."""
        payload = {
            "app_id": self.config.client_id,
            "app_secret": self.config.client_secret,
        }
        
        resp = requests.post(
            self.TENANT_TOKEN_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get tenant token: {data.get('msg')}")
        
        expires_in = data.get("expire", 7200)
        return TokenInfo(
            token=data["tenant_access_token"],
            token_type="tenant",
            expires_at=time.time() + expires_in,
        )
    
    # =========================================================================
    # App Access Token (For store apps, similar to tenant)
    # =========================================================================
    
    def get_app_access_token(self, force_refresh: bool = False) -> str:
        """Get app access token, refreshing if needed."""
        with self._lock:
            token_key = "app"
            
            if not force_refresh and token_key in self._tokens:
                token_info = self._tokens[token_key]
                if not token_info.is_expired():
                    return token_info.token
            
            token_info = self._fetch_app_access_token()
            self._tokens[token_key] = token_info
            self._save_tokens()
            return token_info.token
    
    def _fetch_app_access_token(self) -> TokenInfo:
        """Fetch a new app access token from Lark API."""
        payload = {
            "app_id": self.config.client_id,
            "app_secret": self.config.client_secret,
        }
        
        resp = requests.post(
            self.APP_TOKEN_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get app token: {data.get('msg')}")
        
        expires_in = data.get("expire", 7200)
        return TokenInfo(
            token=data["app_access_token"],
            token_type="app",
            expires_at=time.time() + expires_in,
        )
    
    # =========================================================================
    # User Access Token (Requires initial authorization, then auto-refresh)
    # =========================================================================
    
    def get_user_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """Get user access token, auto-refreshing if possible.
        
        If no user token exists and cannot be refreshed, returns None.
        The caller should then initiate the OAuth flow.
        
        Returns:
            The user access token string, or None if not available
        """
        with self._lock:
            token_key = "user"
            
            if not force_refresh and token_key in self._tokens:
                token_info = self._tokens[token_key]
                if not token_info.is_expired():
                    return token_info.token
                
                # Try to refresh using refresh_token
                if token_info.refresh_token:
                    try:
                        new_token = self._refresh_user_token(token_info.refresh_token)
                        self._tokens[token_key] = new_token
                        self._save_tokens()
                        return new_token.token
                    except Exception as e:
                        print(f"[TokenManager] Failed to refresh user token: {e}")
            
            return None
    
    def set_user_token_from_code(self, auth_code: str) -> str:
        """Exchange authorization code for user access token.
        
        Call this after user completes OAuth authorization in browser.
        
        Args:
            auth_code: The authorization code from OAuth callback
            
        Returns:
            The user access token
        """
        with self._lock:
            token_info = self._fetch_user_token_from_code(auth_code)
            self._tokens["user"] = token_info
            self._save_tokens()
            return token_info.token
    
    def _fetch_user_token_from_code(self, auth_code: str) -> TokenInfo:
        """Exchange authorization code for user access token."""
        payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
        }
        
        # Need app_access_token for this call
        app_token = self.get_app_access_token()
        
        resp = requests.post(
            self.USER_TOKEN_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {app_token}",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get user token: {data.get('msg')}")
        
        token_data = data.get("data", {})
        expires_in = token_data.get("expires_in", 7200)
        
        return TokenInfo(
            token=token_data["access_token"],
            token_type="user",
            expires_at=time.time() + expires_in,
            refresh_token=token_data.get("refresh_token"),
        )
    
    def _refresh_user_token(self, refresh_token: str) -> TokenInfo:
        """Refresh user access token using refresh_token."""
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        
        app_token = self.get_app_access_token()
        
        resp = requests.post(
            self.REFRESH_TOKEN_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {app_token}",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to refresh user token: {data.get('msg')}")
        
        token_data = data.get("data", {})
        expires_in = token_data.get("expires_in", 7200)
        
        return TokenInfo(
            token=token_data["access_token"],
            token_type="user",
            expires_at=time.time() + expires_in,
            refresh_token=token_data.get("refresh_token", refresh_token),
        )
    
    # =========================================================================
    # Token Status & Utilities
    # =========================================================================
    
    def get_token_status(self) -> dict[str, Any]:
        """Get status of all tokens."""
        status = {}
        for key, token_info in self._tokens.items():
            remaining = token_info.expires_at - time.time()
            status[key] = {
                "type": token_info.token_type,
                "expires_at": datetime.fromtimestamp(token_info.expires_at).isoformat(),
                "remaining_seconds": max(0, int(remaining)),
                "is_expired": token_info.is_expired(buffer_seconds=0),
                "needs_refresh": token_info.is_expired(buffer_seconds=300),
                "has_refresh_token": token_info.refresh_token is not None,
            }
        return status
    
    def clear_tokens(self) -> None:
        """Clear all stored tokens."""
        with self._lock:
            self._tokens = {}
            if self._token_file.exists():
                self._token_file.unlink()
    
    def has_valid_user_token(self) -> bool:
        """Check if we have a valid (or refreshable) user token."""
        if "user" not in self._tokens:
            return False
        token_info = self._tokens["user"]
        return not token_info.is_expired() or token_info.refresh_token is not None


# =============================================================================
# Direct Lark API Client (Alternative to MCP for automated operations)
# =============================================================================

class LarkDirectClient:
    """Direct Lark API client using TokenManager for automatic auth.
    
    This bypasses the MCP server and makes direct REST calls to Lark API.
    Use this for automated operations that don't require user interaction.
    """
    
    BASE_URL = "https://open.larksuite.com/open-apis"
    
    def __init__(self, token_manager: Optional[LarkTokenManager] = None):
        self.token_manager = token_manager or LarkTokenManager()
    
    def _get_headers(self, use_user_token: bool = False) -> dict[str, str]:
        """Get authorization headers with auto-refreshed token."""
        if use_user_token:
            token = self.token_manager.get_user_access_token()
            if not token:
                raise RuntimeError("User token not available. Authorization required.")
        else:
            token = self.token_manager.get_tenant_access_token()
        
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    
    def _request(
        self,
        method: str,
        endpoint: str,
        use_user_token: bool = False,
        **kwargs
    ) -> dict[str, Any]:
        """Make an authenticated request to Lark API."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers(use_user_token)
        
        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        
        # Handle HTTP errors with more details
        if resp.status_code >= 400:
            try:
                error_data = resp.json()
                error_msg = error_data.get("msg", error_data.get("error", "Unknown error"))
                error_code = error_data.get("code", resp.status_code)
                raise RuntimeError(
                    f"Lark API error {error_code}: {error_msg} "
                    f"(HTTP {resp.status_code}, endpoint: {endpoint})"
                )
            except (json.JSONDecodeError, RuntimeError) as e:
                if isinstance(e, RuntimeError):
                    raise
                resp.raise_for_status()
        
        data = resp.json()
        
        if data.get("code") != 0:
            raise RuntimeError(f"Lark API error {data.get('code')}: {data.get('msg')}")
        
        return data
    
    # =========================================================================
    # Bitable Operations (using Tenant Access Token)
    # =========================================================================
    
    def list_tables(self, app_token: str) -> list[dict]:
        """List all tables in a Bitable app."""
        data = self._request(
            "GET",
            f"/bitable/v1/apps/{app_token}/tables",
            params={"page_size": 100},
        )
        return data.get("data", {}).get("items", [])
    
    def create_table(
        self,
        app_token: str,
        name: str,
        fields: list[dict[str, Any]],
        default_view_name: str = "Grid View",
    ) -> dict[str, Any]:
        """Create a new table in a Bitable app.
        
        Args:
            app_token: The Bitable app token
            name: Name for the new table
            fields: List of field definitions, e.g.:
                [{"field_name": "Name", "type": 1}, {"field_name": "Status", "type": 3, ...}]
            default_view_name: Name for the default view
            
        Field types:
            1 = Text, 2 = Number, 3 = Single Select, 4 = Multi Select,
            5 = Date, 7 = Checkbox, 11 = Person, 13 = Phone, 15 = URL,
            17 = Attachment, 18 = Link, 19 = Lookup, 20 = Formula,
            21 = Created Time, 22 = Modified Time, 23 = Created By, 1001 = Auto Number
        """
        data = self._request(
            "POST",
            f"/bitable/v1/apps/{app_token}/tables",
            json={
                "table": {
                    "name": name,
                    "default_view_name": default_view_name,
                    "fields": fields,
                }
            },
        )
        return data.get("data", {})
    
    def create_record(
        self,
        app_token: str,
        table_id: str,
        fields: dict[str, Any],
        user_id_type: str = "open_id",
    ) -> dict[str, Any]:
        """Create a record in a Bitable table.
        
        Args:
            app_token: Bitable app token
            table_id: Table ID
            fields: Record fields
            user_id_type: ID type for Person fields ("open_id", "union_id", "user_id")
        """
        data = self._request(
            "POST",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            json={"fields": fields},
            params={"user_id_type": user_id_type},
        )
        return data.get("data", {}).get("record", {})
    
    def get_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
    ) -> dict[str, Any]:
        """Get a record from a Bitable table."""
        data = self._request(
            "GET",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        )
        return data.get("data", {}).get("record", {})
    
    def update_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Update a record in a Bitable table."""
        data = self._request(
            "PUT",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            json={"fields": fields},
        )
        return data.get("data", {}).get("record", {})
    
    def delete_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
    ) -> bool:
        """Delete a record from a Bitable table."""
        self._request(
            "DELETE",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        )
        return True
    
    def search_records(
        self,
        app_token: str,
        table_id: str,
        filter_conditions: Optional[list[dict]] = None,
        field_names: Optional[list[str]] = None,
        page_size: int = 100,
    ) -> list[dict]:
        """Search records in a Bitable table."""
        body: dict[str, Any] = {}
        if filter_conditions:
            body["filter"] = {
                "conjunction": "and",
                "conditions": filter_conditions,
            }
        if field_names:
            body["field_names"] = field_names
        
        data = self._request(
            "POST",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/search",
            json=body,
            params={"page_size": page_size},
        )
        return data.get("data", {}).get("items", [])
    
    # =========================================================================
    # Contact Operations (may require User Access Token for some operations)
    # =========================================================================
    
    def get_user_by_email(self, email: str) -> Optional[dict]:
        """Get user info by email address."""
        try:
            data = self._request(
                "POST",
                "/contact/v3/users/batch_get_id",
                json={"emails": [email]},
                params={"user_id_type": "open_id"},
            )
            user_list = data.get("data", {}).get("user_list", [])
            if user_list:
                return user_list[0]
        except Exception as e:
            print(f"[LarkDirectClient] Failed to get user by email: {e}")
        return None
    
    def get_users_by_emails(self, emails: list[str]) -> dict[str, Optional[str]]:
        """Get user IDs by email addresses."""
        result = {e: None for e in emails}
        
        if not emails:
            return result
        
        try:
            data = self._request(
                "POST",
                "/contact/v3/users/batch_get_id",
                json={"emails": emails},
                params={"user_id_type": "open_id"},
            )
            for item in data.get("data", {}).get("user_list", []):
                email = item.get("email")
                user_id = item.get("user_id")
                if email:
                    result[email] = user_id
        except Exception as e:
            print(f"[LarkDirectClient] Failed to batch get users: {e}")
        
        return result
    
    # =========================================================================
    # Organization/Department Operations
    # =========================================================================
    
    def list_department_users(
        self,
        department_id: str = "0",
        page_size: int = 50,
    ) -> list[dict]:
        """List users in a department (0 = root department = all users).
        
        Requires contact:user.employee_id:readonly or contact:user.base:readonly scope.
        """
        all_users = []
        page_token = None
        
        while True:
            params = {
                "department_id": department_id,
                "page_size": page_size,
                "user_id_type": "open_id",
            }
            if page_token:
                params["page_token"] = page_token
            
            try:
                data = self._request(
                    "GET",
                    "/contact/v3/users",
                    params=params,
                )
                items = data.get("data", {}).get("items", [])
                all_users.extend(items)
                
                page_token = data.get("data", {}).get("page_token")
                if not page_token or not data.get("data", {}).get("has_more"):
                    break
            except Exception as e:
                print(f"[LarkDirectClient] Error listing department users: {e}")
                break
        
        return all_users
    
    def list_all_organization_users(self, page_size: int = 50) -> list[dict]:
        """List all users in the organization (root department)."""
        return self.list_department_users(department_id="0", page_size=page_size)
    
    # =========================================================================
    # Chat/Group Operations
    # =========================================================================
    
    def list_chat_members(self, chat_id: str, page_size: int = 100) -> list[dict]:
        """List members of a Lark group chat.
        
        Args:
            chat_id: The chat/group ID (oc_xxx format)
            page_size: Number of members per page
            
        Returns:
            List of member dicts with member_id, member_id_type, name, etc.
        """
        all_members = []
        page_token = None
        
        while True:
            params = {
                "member_id_type": "open_id",
                "page_size": page_size,
            }
            if page_token:
                params["page_token"] = page_token
            
            try:
                data = self._request(
                    "GET",
                    f"/im/v1/chats/{chat_id}/members",
                    params=params,
                )
                items = data.get("data", {}).get("items", [])
                all_members.extend(items)
                
                page_token = data.get("data", {}).get("page_token")
                if not page_token or not data.get("data", {}).get("has_more"):
                    break
            except Exception as e:
                print(f"[LarkDirectClient] Error listing chat members: {e}")
                break
        
        return all_members
    
    # =========================================================================
    # Document Permission Operations
    # =========================================================================
    
    def transfer_bitable_owner(
        self,
        app_token: str,
        new_owner_id: str,
        new_owner_type: str = "openid",
    ) -> dict:
        """Transfer Bitable ownership to another user.
        
        Args:
            app_token: The Bitable app token
            new_owner_id: The open_id or user_id of the new owner
            new_owner_type: Type of ID ("openid", "userid", "unionid")
        """
        data = self._request(
            "POST",
            f"/drive/v1/permissions/{app_token}/members/transfer_owner",
            json={
                "member_type": "user",
                "member_id": new_owner_id,
            },
            params={"type": "bitable", "need_notification": "true"},
        )
        return data.get("data", {})
    
    def add_bitable_collaborator(
        self,
        app_token: str,
        member_id: str,
        member_type: str = "openid",
        perm: str = "full_access",
    ) -> dict:
        """Add a collaborator to a Bitable document.
        
        Args:
            app_token: The Bitable app token
            member_id: The open_id of the user to add
            member_type: Type of member ("openid", "userid", "email", "chat", "department")
            perm: Permission level ("view", "edit", "full_access")
        """
        data = self._request(
            "POST",
            f"/drive/v1/permissions/{app_token}/members",
            json={
                "member_type": member_type,
                "member_id": member_id,
                "perm": perm,
            },
            params={"type": "bitable", "need_notification": "true"},
        )
        return data.get("data", {})
    
    def list_bitable_collaborators(self, app_token: str) -> list[dict]:
        """List all collaborators of a Bitable document."""
        data = self._request(
            "GET",
            f"/drive/v1/permissions/{app_token}/members",
            params={"type": "bitable"},
        )
        return data.get("data", {}).get("items", [])


# =============================================================================
# Test / CLI Entry Point
# =============================================================================

def main():
    """Test token manager functionality."""
    print("=== Lark Token Manager Test ===\n")
    
    manager = LarkTokenManager()
    
    # Test tenant token
    print("1. Getting Tenant Access Token...")
    try:
        tat = manager.get_tenant_access_token()
        print(f"   Token: {tat[:20]}...{tat[-10:]}")
        print("   SUCCESS")
    except Exception as e:
        print(f"   FAILED: {e}")
    
    # Test token status
    print("\n2. Token Status:")
    status = manager.get_token_status()
    for key, info in status.items():
        print(f"   {key}: expires in {info['remaining_seconds']}s, needs_refresh={info['needs_refresh']}")
    
    # Test direct client
    print("\n3. Testing Direct Client...")
    from src.config import get_lark_bitable_config
    config = get_lark_bitable_config()
    
    if config.app_token and config.tasks_table_id:
        client = LarkDirectClient(manager)
        try:
            tables = client.list_tables(config.app_token)
            print(f"   Found {len(tables)} tables")
            for t in tables[:3]:
                print(f"   - {t.get('name')} ({t.get('table_id')})")
            print("   SUCCESS")
        except Exception as e:
            print(f"   FAILED: {e}")
    else:
        print("   SKIP: No app_token configured")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()
