#!/usr/bin/env python3
"""Live integration tests for GithubAutoLark via the server API.

Tests the multi-step plan execution engine with real API calls.
Run with: python tests/test_integration_live.py
Requires: Server running at localhost:8000
"""

import requests
import sys
import json

BASE_URL = "http://localhost:8000"

PASS = 0
FAIL = 0

def chat(message: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/api/chat",
        json={"message": message},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["response"]

def test(name: str, message: str, expect_any: list[str] = None, expect_none: list[str] = None):
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"CMD:  {message[:80]}{'...' if len(message) > 80 else ''}")
    print(f"{'='*60}")
    
    try:
        response = chat(message)
        print(f"RESP:\n{response[:500]}{'...' if len(response) > 500 else ''}")
        
        ok = True
        if expect_any:
            found = [kw for kw in expect_any if kw.lower() in response.lower()]
            if not found:
                print(f"  [FAIL] Expected any of: {expect_any}")
                ok = False
        if expect_none:
            bad = [kw for kw in expect_none if kw.lower() in response.lower()]
            if bad:
                print(f"  [FAIL] Should NOT contain: {bad}")
                ok = False
        
        if ok:
            print("  [PASS]")
            PASS += 1
        else:
            FAIL += 1
        return ok
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        FAIL += 1
        return False

def main():
    print("=" * 60)
    print("MULTI-STEP ENGINE INTEGRATION TESTS")
    print("=" * 60)

    # Check server
    try:
        resp = requests.get(f"{BASE_URL}/api/status", timeout=5)
        data = resp.json()
        print(f"Server: OK | LLM: {data['llm']['model']}")
    except Exception as e:
        print(f"Server not available: {e}")
        sys.exit(1)

    # === BASIC SINGLE-STEP COMMANDS ===

    test("List Members (empty)", "list members",
         expect_any=["member", "No"])

    test("Fetch GitHub Members", "fetch github members",
         expect_any=["GitHub", "collaborator"])

    test("Fetch Lark Members", "fetch lark members",
         expect_any=["Lark"])

    test("List Members (populated)", "list members",
         expect_any=["member"])

    test("List Open Issues", "list open issues",
         expect_any=["issue"])

    test("Sync Status", "sync status",
         expect_any=["Pending"])

    # === COMPOUND COMMANDS ===

    test("Link + Query",
         "link KataDavidXD to Yang Li, then show what Yang Li is doing",
         expect_any=["Yang Li", "Step"],
         expect_none=["couldn't understand"])

    test("Chinese Work Query", "Yang Li\u5728\u505a\u4ec0\u4e48",
         expect_any=["Yang Li"],
         expect_none=["couldn't understand"])

    test("List Tables", "list tables",
         expect_none=["couldn't understand"])

    # === THE PROFESSOR'S REAL COMMAND ===

    test("Create Table with Tasks (Chinese/English)",
         "\u521b\u5efa\u4e00\u4e2a\u65b0\u8868\uff0c\u4ee5\u53ca\u4efb\u52a1\uff1aYang Li - SDK packaging, Ethan Chen - \u8fc1\u79fBdemo\u5230v0.5.2, Di - mas agent\u4f18\u5316",
         expect_any=["table", "created", "task", "SDK"],
         expect_none=["couldn't understand"])

    # === SUMMARY ===
    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
    print(f"{'='*60}")

    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
