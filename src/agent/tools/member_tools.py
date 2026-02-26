"""Tool functions for the Member Management agent.

Each function is a plain callable that wraps MemberService.
These are designed to be bound to a LangGraph ``create_react_agent``
via ``langchain_core.tools.tool`` or used directly.
"""

from __future__ import annotations

from typing import Any, Optional

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.models.member import Member, MemberRole
from src.services.member_service import MemberService


class MemberTools:
    """Stateful tool collection — holds references to DB and services."""

    def __init__(self, db: Database, lark_service: Any = None, github_service: Any = None):
        self._db = db
        self._svc = MemberService(db, lark_service=lark_service, github_service=github_service)
        self._lark = lark_service
        self._github = github_service
        self._member_repo = MemberRepository(db)

    def create_member(
        self,
        name: str,
        email: str,
        role: str = "member",
        position: Optional[str] = None,
        team: Optional[str] = None,
        github_username: Optional[str] = None,
    ) -> str:
        """Create a new team member with cross-platform identity resolution."""
        try:
            member = self._svc.create_member(
                name=name, email=email, role=role,
                position=position, team=team,
                github_username=github_username,
            )
            lark_status = f", Lark ID: {member.lark_open_id}" if member.lark_open_id else ""
            return (
                f"Member '{member.name}' created (ID: {member.member_id[:8]}). "
                f"Email: {member.email}, Role: {member.role.value}{lark_status}"
            )
        except Exception as e:
            return f"Error creating member: {e}"

    def get_member(self, identifier: str) -> str:
        """Look up a member by email, name, or ID."""
        member = self._svc.get_member(identifier)
        if not member:
            return f"Member '{identifier}' not found."
        lines = [
            f"Name: {member.name}",
            f"Email: {member.email}",
            f"Role: {member.role.value}",
            f"Position: {member.position or 'N/A'}",
            f"Team: {member.team or 'N/A'}",
            f"GitHub: {member.github_username or 'N/A'}",
            f"Lark ID: {member.lark_open_id or 'N/A'}",
            f"Status: {member.status.value}",
            f"Tables: {', '.join(t.table_name for t in member.lark_tables) or 'None'}",
        ]
        return "\n".join(lines)

    def update_member(self, identifier: str, **fields: Any) -> str:
        """Update member fields (role, position, team, github_username, etc.)."""
        result = self._svc.update_member(identifier, **fields)
        if not result:
            return f"Member '{identifier}' not found."
        return f"Member '{result.name}' updated successfully."

    def set_member_alias(self, current_name: str, new_name: str) -> str:
        """Update a member's name (useful for adding Chinese/English name mapping)."""
        members = self._member_repo.find_by_name(current_name)
        if not members:
            return f"Member '{current_name}' not found."
        
        member = members[0]
        self._member_repo.update(member.member_id, name=new_name)
        return f"Member name updated: '{current_name}' -> '{new_name}'"

    def bulk_rename_members(self, name_mapping: dict[str, str]) -> str:
        """Bulk rename members. Example: {"Yang Li": "李阳 (Yang Li)"}"""
        results = []
        for old_name, new_name in name_mapping.items():
            members = self._member_repo.find_by_name(old_name)
            if members:
                self._member_repo.update(members[0].member_id, name=new_name)
                results.append(f"'{old_name}' -> '{new_name}'")
            else:
                results.append(f"'{old_name}' NOT FOUND")
        return f"Renamed {len([r for r in results if 'NOT FOUND' not in r])}/{len(name_mapping)} members:\n" + "\n".join(results)

    def list_members(
        self,
        role: Optional[str] = None,
        team: Optional[str] = None,
        status: str = "active",
    ) -> str:
        """List team members with optional filters."""
        members = self._svc.list_members(role=role, team=team, status=status)
        if not members:
            return "No members found matching filters."
        lines = [f"Found {len(members)} member(s):"]
        for m in members:
            # Build identity info
            identities = []
            if m.github_username:
                identities.append(f"GitHub: {m.github_username}")
            if m.lark_open_id:
                identities.append(f"Lark: {m.lark_open_id[:12]}...")
            identity_str = " | ".join(identities) if identities else "No linked accounts"
            
            lines.append(
                f"  - {m.name} ({m.email}) [{m.role.value}]\n"
                f"      {identity_str}"
            )
        return "\n".join(lines)

    def deactivate_member(self, identifier: str) -> str:
        """Soft-delete a member (mark as inactive)."""
        result = self._svc.deactivate_member(identifier)
        if not result:
            return f"Member '{identifier}' not found."
        return f"Member '{result.name}' deactivated."

    def assign_table(self, identifier: str, table_name: str) -> str:
        """Assign a Lark table to a member."""
        try:
            result = self._svc.assign_table(identifier, table_name)
            if not result:
                return f"Member '{identifier}' not found."
            tables = ", ".join(t.table_name for t in result.lark_tables)
            return f"Member '{result.name}' assigned to tables: {tables}"
        except ValueError as e:
            return str(e)

    def view_member_work(self, identifier: str) -> str:
        """View all GitHub issues and Lark records for a member.
        
        Searches BOTH platforms:
        - GitHub: Issues assigned to the member's GitHub username
        - Lark: Records with Assignee field matching the member's Lark ID
        """
        work = self._svc.get_member_work(identifier)
        if not work:
            # Try to find by GitHub username directly
            member = self._member_repo.get_by_github(identifier)
            if member:
                work = self._svc.get_member_work(member.email)
            if not work:
                return f"Member '{identifier}' not found."
        
        # Add helpful info about missing identities
        result = work.to_text()
        missing = []
        if not work.member.github_username:
            missing.append("GitHub username not linked - cannot search GitHub issues")
        if not work.member.lark_open_id:
            missing.append("Lark ID not linked - cannot search Lark records")
        
        if missing and work.total_items == 0:
            result += "\n\nNote:\n  " + "\n  ".join(missing)
            result += "\n\nTip: Link identities with 'link <github_username> to <member_name>'"
        
        return result

    # =========================================================================
    # GitHub Member Operations
    # =========================================================================

    def fetch_github_members(self) -> str:
        """Fetch all collaborators from GitHub repository and save to local DB."""
        if not self._github:
            return "Error: GitHub service not configured."
        
        try:
            collaborators = self._github.list_repo_collaborators()
            synced = 0
            
            for collab in collaborators:
                username = collab.get("login")
                if not username:
                    continue
                
                existing = self._member_repo.get_by_github(username)
                if existing:
                    continue
                
                user_details = self._github.get_user(username)
                email = user_details.get("email") or f"{username}@github.local"
                name = user_details.get("name") or username
                
                member = Member(
                    name=name,
                    email=email,
                    github_username=username,
                    role=MemberRole.DEVELOPER,
                )
                self._member_repo.create(member)
                synced += 1
            
            total = len(collaborators)
            return f"GitHub: Found {total} collaborators, synced {synced} new members to local DB."
        
        except Exception as e:
            return f"Error fetching GitHub members: {e}"

    # =========================================================================
    # Lark Organization Member Operations
    # =========================================================================

    def fetch_lark_members(self) -> str:
        """Fetch Lark members from group chat or organization.
        
        Uses LARK_TEAM_CHAT_ID if configured, otherwise tries organization API.
        """
        import os
        chat_id = os.getenv("LARK_TEAM_CHAT_ID")
        
        if chat_id:
            return self._fetch_lark_members_from_chat(chat_id)
        
        if not self._lark:
            return "Error: Lark service not configured. Set LARK_TEAM_CHAT_ID in .env."
        
        try:
            self._lark._init_direct_client()
            users = self._lark.direct.list_all_organization_users()
            synced = 0
            
            for user in users:
                open_id = user.get("open_id")
                email = user.get("email")
                name = user.get("name")
                
                if not open_id or not name:
                    continue
                
                existing = self._member_repo.get_by_lark_id(open_id)
                if existing:
                    continue
                
                if email:
                    existing_by_email = self._member_repo.get_by_email(email)
                    if existing_by_email:
                        self._member_repo.update(existing_by_email.member_id, lark_open_id=open_id)
                        synced += 1
                        continue
                
                member = Member(
                    name=name,
                    email=email or f"{open_id}@lark.local",
                    lark_open_id=open_id,
                    role=MemberRole.MEMBER,
                )
                self._member_repo.create(member)
                synced += 1
            
            total = len(users)
            return f"Lark: Found {total} organization users, synced {synced} to local DB."
        
        except Exception as e:
            return f"Error fetching Lark members: {e}. Consider setting LARK_TEAM_CHAT_ID."

    def _fetch_lark_members_from_chat(self, chat_id: str) -> str:
        """Fetch members from a Lark group chat via direct API."""
        if not self._lark:
            return "Error: Lark service not configured."
        
        try:
            self._lark._init_direct_client()
            members = self._lark.direct.list_chat_members(chat_id)
            synced = 0
            
            for m in members:
                member_type = m.get("member_id_type", "")
                member_id = m.get("member_id", "")
                name = m.get("name", "")
                
                if member_type != "open_id" or not member_id:
                    continue
                
                existing = self._member_repo.get_by_lark_id(member_id)
                if existing:
                    continue
                
                member = Member(
                    name=name or f"Lark User {member_id[:8]}",
                    email=f"{member_id}@lark.local",
                    lark_open_id=member_id,
                    role=MemberRole.MEMBER,
                )
                self._member_repo.create(member)
                synced += 1
            
            return f"Lark Chat: Found {len(members)} members, synced {synced} new to local DB."
        
        except Exception as e:
            return f"Error fetching chat members: {e}"

    # =========================================================================
    # Member Binding Operations
    # =========================================================================

    def link_members(
        self,
        member1_name: str,
        member2_name: str,
    ) -> str:
        """Link two member records as the same person (merge identities).
        
        This merges GitHub and Lark identities from both records into one,
        keeping the member with Lark identity and adding GitHub identity.
        
        Args:
            member1_name: One member (could be name or GitHub username)
            member2_name: Other member (could be name or GitHub username)
        
        Example: "link KataDavidXD to Yang Li" - finds GitHub user and Lark user, merges them
        """
        # Smart member resolution - try to find DISTINCT members
        # member2_name might be a GitHub username
        m_github = self._member_repo.get_by_github(member2_name)
        if not m_github:
            m_github = self._member_repo.get_by_github(member1_name)
        
        # Find members by name, preferring one with Lark identity
        all_by_name = []
        for name in [member1_name, member2_name]:
            results = self._member_repo.find_by_name(name)
            for r in results:
                if r not in all_by_name:
                    all_by_name.append(r)
        
        # Find the Lark member (has lark_open_id, no github_username)
        m_lark = None
        for m in all_by_name:
            if m.lark_open_id and not m.github_username:
                m_lark = m
                break
        
        # If we found both a GitHub member and a Lark member, link them
        if m_github and m_lark and m_github.member_id != m_lark.member_id:
            m1 = m_lark  # Keep the Lark member as primary
            m2 = m_github  # Merge GitHub identity into it
        elif m_github and not m_lark:
            # Only found GitHub member, look for Lark member by name
            m2 = m_github
            m1_results = [m for m in all_by_name if m.member_id != m2.member_id]
            m1 = m1_results[0] if m1_results else None
            if not m1:
                return f"Cannot find a distinct Lark member to link with '{member2_name}'"
        else:
            # Fallback to original logic
            m1_results = self._member_repo.find_by_name(member1_name)
            m1 = m1_results[0] if m1_results else self._member_repo.get_by_github(member1_name)
            
            m2_results = self._member_repo.find_by_name(member2_name)
            m2 = m2_results[0] if m2_results else self._member_repo.get_by_github(member2_name)
        
        if not m1:
            return f"Member '{member1_name}' not found."
        if not m2:
            return f"Member '{member2_name}' not found."
        
        if m1.member_id == m2.member_id:
            return f"'{member1_name}' and '{member2_name}' are already the same member."
        
        # Collect identities to merge from m2 into m1
        updates = {}
        merged_info = []
        
        if m2.github_username and not m1.github_username:
            updates["github_username"] = m2.github_username
            merged_info.append(f"GitHub: {m2.github_username}")
        
        if m2.lark_open_id and not m1.lark_open_id:
            updates["lark_open_id"] = m2.lark_open_id
            merged_info.append(f"Lark ID: {m2.lark_open_id[:12]}...")
        
        # Check if we should update email (only if m1 has placeholder and m2 has real)
        should_update_email = (
            m2.email and 
            "@lark.local" in m1.email and 
            "@lark.local" not in m2.email
        )
        
        # Delete the secondary member FIRST to avoid unique constraint on email
        m2_email = m2.email
        m2_name = m2.name
        self._member_repo.delete(m2.member_id)
        
        # Now update email if needed
        if should_update_email:
            updates["email"] = m2_email
            merged_info.append(f"Email: {m2_email}")
        
        # Apply updates to primary member
        if updates:
            self._member_repo.update(m1.member_id, **updates)
        
        if merged_info:
            return f"Linked '{m1.name}' with '{m2_name}'. Merged: {', '.join(merged_info)}. Deleted duplicate."
        else:
            return f"Linked '{m1.name}' with '{m2_name}'. No new identities to merge. Deleted duplicate."

    def bind_member(
        self,
        identifier: str,
        github_username: Optional[str] = None,
        lark_open_id: Optional[str] = None,
        lark_email: Optional[str] = None,
    ) -> str:
        """Bind GitHub and Lark identities to a local member.
        
        Args:
            identifier: Member name, email, or ID
            github_username: GitHub username to bind
            lark_open_id: Lark open_id to bind
            lark_email: Use email to look up Lark open_id
        """
        member = self._svc.get_member(identifier)
        if not member:
            return f"Member '{identifier}' not found."
        
        updates = {}
        
        if github_username:
            updates["github_username"] = github_username
        
        if lark_open_id:
            updates["lark_open_id"] = lark_open_id
        elif lark_email and self._lark:
            try:
                self._lark._init_direct_client()
                user = self._lark.direct.get_user_by_email(lark_email)
                if user and user.get("user_id"):
                    updates["lark_open_id"] = user.get("user_id")
            except Exception as e:
                return f"Error looking up Lark user by email: {e}"
        
        if not updates:
            return "No binding information provided."
        
        result = self._svc.update_member(identifier, **updates)
        if not result:
            return "Failed to update member."
        
        return (
            f"Member '{result.name}' bound successfully.\n"
            f"  GitHub: {result.github_username or 'Not set'}\n"
            f"  Lark ID: {result.lark_open_id or 'Not set'}"
        )

    def sync_all_members(self) -> str:
        """Fetch members from both GitHub and Lark, merge by email."""
        results = []
        
        github_result = self.fetch_github_members()
        results.append(github_result)
        
        lark_result = self.fetch_lark_members()
        results.append(lark_result)
        
        members = self._member_repo.list_all()
        for m in members:
            if m.github_username and not m.lark_open_id and m.email and self._lark:
                try:
                    self._lark._init_direct_client()
                    user = self._lark.direct.get_user_by_email(m.email)
                    if user and user.get("user_id"):
                        self._member_repo.update(m.member_id, lark_open_id=user.get("user_id"))
                except Exception:
                    pass
            
            elif m.lark_open_id and not m.github_username and m.email:
                pass
        
        total = len(self._member_repo.list_all())
        results.append(f"Total members in local DB: {total}")
        
        return "\n".join(results)

    # =========================================================================
    # Lark Permission Operations
    # =========================================================================

    def transfer_lark_permission(
        self,
        target_name: str,
        permission: str = "full_access",
    ) -> str:
        """Transfer Lark Bitable permission to a user.
        
        Args:
            target_name: Name or email of the user to grant permission
            permission: Permission level (view, edit, full_access)
        """
        if not self._lark:
            return "Error: Lark service not configured."
        
        member = self._svc.get_member(target_name)
        if not member:
            results = self._member_repo.find_by_name(target_name)
            member = results[0] if results else None
        
        if not member:
            return f"Member '{target_name}' not found in local DB."
        
        if not member.lark_open_id:
            if member.email and self._lark:
                try:
                    self._lark._init_direct_client()
                    user = self._lark.direct.get_user_by_email(member.email)
                    if user and user.get("user_id"):
                        member.lark_open_id = user.get("user_id")
                        self._member_repo.update(member.member_id, lark_open_id=member.lark_open_id)
                except Exception as e:
                    return f"Error looking up Lark ID for {target_name}: {e}"
        
        if not member.lark_open_id:
            return f"Member '{target_name}' has no Lark ID. Cannot transfer permission."
        
        try:
            self._lark._init_direct_client()
            result = self._lark.direct.add_bitable_collaborator(
                self._lark.config.app_token,
                member.lark_open_id,
                perm=permission,
            )
            return f"Permission '{permission}' granted to '{member.name}' ({member.lark_open_id[:12]}...) on Bitable."
        except Exception as e:
            return f"Error transferring permission: {e}"

    def transfer_lark_ownership(self, target_name: str) -> str:
        """Transfer Lark Bitable ownership to a user.
        
        Args:
            target_name: Name or email of the new owner
        """
        if not self._lark:
            return "Error: Lark service not configured."
        
        member = self._svc.get_member(target_name)
        if not member:
            results = self._member_repo.find_by_name(target_name)
            member = results[0] if results else None
        
        if not member:
            return f"Member '{target_name}' not found."
        
        if not member.lark_open_id:
            return f"Member '{target_name}' has no Lark ID."
        
        try:
            result = self._lark.transfer_bitable_owner(member.lark_open_id)
            return f"Bitable ownership transferred to '{member.name}'."
        except Exception as e:
            return f"Error transferring ownership: {e}"

    def list_lark_collaborators(self) -> str:
        """List all collaborators on the Lark Bitable."""
        if not self._lark:
            return "Error: Lark service not configured."
        
        try:
            self._lark._init_direct_client()
            collaborators = self._lark.direct.list_bitable_collaborators(
                self._lark.config.app_token
            )
            
            if not collaborators:
                return "No collaborators found on Bitable."
            
            lines = [f"Bitable Collaborators ({len(collaborators)}):"]
            for c in collaborators:
                member_type = c.get("member_type", "unknown")
                member_id = c.get("member_id", "")[:12]
                perm = c.get("perm", "unknown")
                lines.append(f"  - {member_type}: {member_id}... ({perm})")
            
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing collaborators: {e}"
