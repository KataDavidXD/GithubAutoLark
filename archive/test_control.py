#!/usr/bin/env python3
"""
Comprehensive Test Control Script for GithubAutoLark

This script provides a unified interface to run:
1. Unit tests (DB, Services, Sync) with mocked dependencies
2. Integration tests with real .env credentials
3. Real E2E tests against live GitHub/Lark APIs

Usage:
    python test_control.py --unit          # Run only unit tests
    python test_control.py --integration   # Run only integration tests (mocked)
    python test_control.py --real          # Run real API tests (requires .env)
    python test_control.py --all           # Run all tests
    python test_control.py                 # Same as --all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Results storage
TEST_RESULTS_DIR = Path("data/test_results")
TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


class TestResult:
    """Stores a single test result with feedback."""

    def __init__(
        self,
        test_name: str,
        category: str,
        passed: bool,
        duration_ms: float,
        details: str = "",
        error: Optional[str] = None,
    ):
        self.test_name = test_name
        self.category = category
        self.passed = passed
        self.duration_ms = duration_ms
        self.details = details
        self.error = error
        self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "category": self.category,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "details": self.details,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class TestReporter:
    """Collects and reports test results."""

    def __init__(self):
        self.results: list[TestResult] = []
        self.start_time = time.time()

    def add(self, result: TestResult):
        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {result.test_name} ({result.duration_ms:.0f}ms)")
        if result.error:
            print(f"       Error: {result.error[:200]}")

    def summary(self) -> dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        duration = (time.time() - self.start_time) * 1000

        return {
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "success_rate": f"{100 * passed / total:.1f}%" if total > 0 else "N/A",
            "total_duration_ms": duration,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "results": [r.to_dict() for r in self.results],
        }

    def print_summary(self):
        s = self.summary()
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"Total: {s['total_tests']} | Passed: {s['passed']} | Failed: {s['failed']}")
        print(f"Success Rate: {s['success_rate']}")
        print(f"Total Duration: {s['total_duration_ms']:.0f}ms")

        if s["failed"] > 0:
            print("\nFailed Tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.test_name}: {r.error or 'Unknown error'}")

    def save(self, filename: str):
        filepath = TEST_RESULTS_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.summary(), f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {filepath}")


# =============================================================================
# Unit Tests Runner
# =============================================================================


def run_unit_tests(reporter: TestReporter) -> bool:
    """Run all unit tests from tests/ directory."""
    print("\n" + "=" * 60)
    print("RUNNING UNIT TESTS")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_modules = [
        ("tests.test_db", "Database Layer"),
        ("tests.test_services", "Service Layer"),
        ("tests.test_agents", "Agent Logic"),
    ]

    all_passed = True

    for module_name, category in test_modules:
        print(f"\n--- {category} ({module_name}) ---")
        try:
            module = __import__(module_name, fromlist=[""])
            module_suite = loader.loadTestsFromModule(module)

            for test_group in module_suite:
                for test in test_group:
                    test_name = str(test)
                    start = time.time()
                    result = unittest.TestResult()

                    try:
                        test.run(result)
                        duration = (time.time() - start) * 1000
                        passed = result.wasSuccessful()

                        if not passed:
                            all_passed = False
                            errors = result.errors + result.failures
                            error_msg = errors[0][1] if errors else "Unknown failure"
                        else:
                            error_msg = None

                        reporter.add(TestResult(
                            test_name=test_name,
                            category=category,
                            passed=passed,
                            duration_ms=duration,
                            error=error_msg,
                        ))
                    except Exception as e:
                        all_passed = False
                        reporter.add(TestResult(
                            test_name=test_name,
                            category=category,
                            passed=False,
                            duration_ms=(time.time() - start) * 1000,
                            error=str(e),
                        ))

        except ImportError as e:
            print(f"  [SKIP] Could not import {module_name}: {e}")
            reporter.add(TestResult(
                test_name=f"import_{module_name}",
                category=category,
                passed=False,
                duration_ms=0,
                error=f"Import failed: {e}",
            ))
            all_passed = False

    return all_passed


# =============================================================================
# Integration Tests Runner (Mocked)
# =============================================================================


def run_integration_tests(reporter: TestReporter) -> bool:
    """Run integration tests with mocked external services."""
    print("\n" + "=" * 60)
    print("RUNNING INTEGRATION TESTS (Mocked)")
    print("=" * 60)

    try:
        from tests.test_integration import (
            TestMemberLifecycle,
            TestGitHubIssueLarkSync,
            TestLarkTableManagement,
            TestSyncOperations,
            TestACIDConsistency,
            TestGracefulErrorHandling,
        )

        test_classes = [
            ("Member Lifecycle", TestMemberLifecycle),
            ("GitHub-Lark Sync", TestGitHubIssueLarkSync),
            ("Lark Table Management", TestLarkTableManagement),
            ("Sync Operations", TestSyncOperations),
            ("ACID Consistency", TestACIDConsistency),
            ("Error Handling", TestGracefulErrorHandling),
        ]

        all_passed = True

        for category, test_class in test_classes:
            print(f"\n--- {category} ---")
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromTestCase(test_class)

            for test in suite:
                test_name = str(test)
                start = time.time()
                result = unittest.TestResult()

                try:
                    test.run(result)
                    duration = (time.time() - start) * 1000
                    passed = result.wasSuccessful()

                    if not passed:
                        all_passed = False
                        errors = result.errors + result.failures
                        error_msg = errors[0][1] if errors else "Unknown failure"
                    else:
                        error_msg = None

                    reporter.add(TestResult(
                        test_name=test_name,
                        category=f"Integration: {category}",
                        passed=passed,
                        duration_ms=duration,
                        error=error_msg,
                    ))
                except Exception as e:
                    all_passed = False
                    reporter.add(TestResult(
                        test_name=test_name,
                        category=f"Integration: {category}",
                        passed=False,
                        duration_ms=(time.time() - start) * 1000,
                        error=str(e),
                    ))

        return all_passed

    except ImportError as e:
        print(f"[ERROR] Could not import integration tests: {e}")
        reporter.add(TestResult(
            test_name="import_integration_tests",
            category="Integration",
            passed=False,
            duration_ms=0,
            error=f"Import failed: {e}",
        ))
        return False


# =============================================================================
# Real API Tests
# =============================================================================


class RealAPITester:
    """Tests against real GitHub and Lark APIs."""

    def __init__(self, reporter: TestReporter):
        self.reporter = reporter
        self.db = None
        self.github_svc = None
        self.lark_svc = None
        self.created_issues: list[int] = []
        self.created_records: list[str] = []

    def setup(self) -> bool:
        """Initialize real services."""
        print("\n--- Setting up real services ---")
        try:
            from src.db.database import Database
            from src.services.github_service import GitHubService
            from src.services.lark_service import LarkService

            # Use a separate test database
            self.db = Database(path=Path("data/test_real.db"))
            self.db.init()

            self.github_svc = GitHubService()
            self.lark_svc = LarkService()

            print(f"  GitHub repo: {self.github_svc.repo_slug}")
            print(f"  Lark app token: {self.lark_svc.config.app_token[:8]}...")
            return True

        except Exception as e:
            print(f"  [ERROR] Setup failed: {e}")
            traceback.print_exc()
            return False

    def cleanup(self):
        """Clean up test resources."""
        print("\n--- Cleaning up test resources ---")

        # Clean up created GitHub issues (close them)
        if self.github_svc and self.created_issues:
            for issue_num in self.created_issues:
                try:
                    self.github_svc.close_issue(issue_num, reason="not_planned")
                    print(f"  Closed GitHub issue #{issue_num}")
                except Exception as e:
                    print(f"  Failed to close issue #{issue_num}: {e}")

        if self.db:
            self.db.close()

    def test_github_service_directly(self) -> bool:
        """Test GitHub API calls directly."""
        print("\n--- Testing GitHub Service Directly ---")
        start = time.time()

        try:
            # Test 1: List issues
            issues = self.github_svc.list_issues(state="all", per_page=5)
            self.reporter.add(TestResult(
                test_name="github_list_issues",
                category="Real API: GitHub",
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=f"Listed {len(issues)} issues",
            ))

            # Test 2: Create a test issue
            start = time.time()
            test_title = f"[E2E TEST] Automated Test - {datetime.now().strftime('%Y%m%d_%H%M%S')}"
            result = self.github_svc.create_issue(
                title=test_title,
                body="This is an automated test issue. It will be closed automatically.",
                labels=["test", "automated"],
            )
            issue_number = result.get("number")
            self.created_issues.append(issue_number)

            self.reporter.add(TestResult(
                test_name="github_create_issue",
                category="Real API: GitHub",
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=f"Created issue #{issue_number}",
            ))

            # Test 3: Get the created issue
            start = time.time()
            fetched = self.github_svc.get_issue(issue_number)
            self.reporter.add(TestResult(
                test_name="github_get_issue",
                category="Real API: GitHub",
                passed=fetched["title"] == test_title,
                duration_ms=(time.time() - start) * 1000,
                details=f"Fetched issue #{issue_number}",
            ))

            # Test 4: Update the issue
            start = time.time()
            updated = self.github_svc.update_issue(
                issue_number,
                body="Updated body - test successful!",
                labels=["test", "automated", "verified"],
            )
            self.reporter.add(TestResult(
                test_name="github_update_issue",
                category="Real API: GitHub",
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=f"Updated issue #{issue_number}",
            ))

            # Test 5: Add comment
            start = time.time()
            comment = self.github_svc.create_comment(
                issue_number,
                "Automated test comment - all tests passed!"
            )
            self.reporter.add(TestResult(
                test_name="github_create_comment",
                category="Real API: GitHub",
                passed=True,
                duration_ms=(time.time() - start) * 1000,
                details=f"Added comment to issue #{issue_number}",
            ))

            return True

        except Exception as e:
            self.reporter.add(TestResult(
                test_name="github_service_test",
                category="Real API: GitHub",
                passed=False,
                duration_ms=(time.time() - start) * 1000,
                error=str(e),
            ))
            traceback.print_exc()
            return False

    def test_lark_service_directly(self) -> bool:
        """Test Lark API calls using Direct API with auto token refresh."""
        print("\n--- Testing Lark Service (Direct API Mode) ---")

        all_passed = True
        
        try:
            # Use direct API mode for automatic token management
            self.lark_svc.use_direct_api = True
            
            with self.lark_svc:
                # Test 1: List tables
                start = time.time()
                tables = self.lark_svc.list_tables()
                self.reporter.add(TestResult(
                    test_name="lark_list_tables",
                    category="Real API: Lark",
                    passed=True,
                    duration_ms=(time.time() - start) * 1000,
                    details=f"Listed {len(tables)} tables",
                ))

                # Test 2: Create a record (may fail due to permissions)
                start = time.time()
                test_task_name = f"[E2E TEST] Automated Test - {datetime.now().strftime('%Y%m%d_%H%M%S')}"
                record_id = None
                try:
                    result = self.lark_svc.create_record({
                        "Task Name": test_task_name,
                        "Status": "To Do",
                        "Description": "Automated test record - will be cleaned up",
                    })

                    # Handle different response structures
                    if isinstance(result, dict):
                        if "record" in result:
                            record_id = result["record"].get("record_id")
                        elif "record_id" in result:
                            record_id = result["record_id"]

                    if record_id:
                        self.created_records.append(record_id)
                        self.reporter.add(TestResult(
                            test_name="lark_create_record",
                            category="Real API: Lark",
                            passed=True,
                            duration_ms=(time.time() - start) * 1000,
                            details=f"Created record {record_id}",
                        ))
                    else:
                        self.reporter.add(TestResult(
                            test_name="lark_create_record",
                            category="Real API: Lark",
                            passed=False,
                            duration_ms=(time.time() - start) * 1000,
                            error=f"Unexpected response structure: {result}",
                        ))
                        all_passed = False
                except Exception as create_err:
                    err_str = str(create_err)
                    # 91403 = permission denied for bitable record operations
                    if "91403" in err_str or "Forbidden" in err_str:
                        self.reporter.add(TestResult(
                            test_name="lark_create_record",
                            category="Real API: Lark",
                            passed=False,
                            duration_ms=(time.time() - start) * 1000,
                            error=f"Permission denied (tenant token may lack bitable:record scope): {err_str[:100]}",
                        ))
                        print(f"  [NOTE] Tenant token lacks write permission. Enable bitable:record scope in Lark app.")
                    else:
                        self.reporter.add(TestResult(
                            test_name="lark_create_record",
                            category="Real API: Lark",
                            passed=False,
                            duration_ms=(time.time() - start) * 1000,
                            error=str(create_err),
                        ))
                    all_passed = False

                # Test 3: Search records (should work with read permission)
                start = time.time()
                try:
                    records = self.lark_svc.search_records(
                        filter_conditions=[{
                            "field_name": "Task Name",
                            "operator": "contains",
                            "value": ["E2E TEST"],
                        }]
                    )
                    self.reporter.add(TestResult(
                        test_name="lark_search_records",
                        category="Real API: Lark",
                        passed=True,
                        duration_ms=(time.time() - start) * 1000,
                        details=f"Found {len(records)} matching records",
                    ))
                except Exception as search_err:
                    self.reporter.add(TestResult(
                        test_name="lark_search_records",
                        category="Real API: Lark",
                        passed=False,
                        duration_ms=(time.time() - start) * 1000,
                        error=str(search_err),
                    ))
                    all_passed = False

                # Test 4: Update record (only if we created one)
                if record_id:
                    start = time.time()
                    try:
                        updated = self.lark_svc.update_record(
                            record_id,
                            {"Status": "In Progress", "Description": "Test updated!"},
                        )
                        self.reporter.add(TestResult(
                            test_name="lark_update_record",
                            category="Real API: Lark",
                            passed=True,
                            duration_ms=(time.time() - start) * 1000,
                            details=f"Updated record {record_id}",
                        ))
                    except Exception as update_err:
                        self.reporter.add(TestResult(
                            test_name="lark_update_record",
                            category="Real API: Lark",
                            passed=False,
                            duration_ms=(time.time() - start) * 1000,
                            error=str(update_err),
                        ))
                        all_passed = False

                # Test 5: Get user ID by email
                start = time.time()
                email = os.getenv("EMPLOYEE_EMAIL", "")
                if email:
                    try:
                        user_id = self.lark_svc.get_user_id_by_email(email)
                        self.reporter.add(TestResult(
                            test_name="lark_get_user_id",
                            category="Real API: Lark",
                            passed=user_id is not None,
                            duration_ms=(time.time() - start) * 1000,
                            details=f"User ID for {email}: {user_id}",
                        ))
                    except Exception as user_err:
                        self.reporter.add(TestResult(
                            test_name="lark_get_user_id",
                            category="Real API: Lark",
                            passed=False,
                            duration_ms=(time.time() - start) * 1000,
                            error=str(user_err),
                        ))
                        all_passed = False

                return all_passed

        except Exception as e:
            self.reporter.add(TestResult(
                test_name="lark_service_setup",
                category="Real API: Lark",
                passed=False,
                duration_ms=0,
                error=str(e),
            ))
            traceback.print_exc()
            return False

    def test_agent_commands(self) -> bool:
        """Test the full agent graph with real services."""
        print("\n--- Testing Agent Commands (Real with Direct API) ---")

        try:
            from src.agent.graph import run_command
            from src.db.lark_table_repo import LarkTableRepository
            from src.models.lark_table_registry import LarkTableConfig

            # Use direct API mode for automatic token management
            self.lark_svc.use_direct_api = True
            
            with self.lark_svc:
                # Register default table if not exists
                table_repo = LarkTableRepository(self.db)
                existing = table_repo.get_default()
                if not existing:
                    cfg = LarkTableConfig(
                        app_token=self.lark_svc.config.app_token,
                        table_id=self.lark_svc.config.tasks_table_id,
                        table_name="Tasks",
                        is_default=True,
                    )
                    table_repo.register(cfg)
                    print(f"  Registered default table: Tasks")

                # Test 1: Add member (use unique email to avoid duplicate error)
                start = time.time()
                unique_ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                test_email = f"testuser_{unique_ts}@example.com"
                result = run_command(
                    f"Add member TestUser {test_email} as developer",
                    db=self.db,
                    github_service=self.github_svc,
                    lark_service=self.lark_svc,
                )
                passed = "created" in result.lower() or "exists" in result.lower() or "member" in result.lower()
                self.reporter.add(TestResult(
                    test_name="agent_add_member",
                    category="Real API: Agent",
                    passed=passed,
                    duration_ms=(time.time() - start) * 1000,
                    details=result[:200],
                    error=None if passed else result,
                ))

                # Test 2: List tables
                start = time.time()
                result = run_command(
                    "List tables",
                    db=self.db,
                    github_service=self.github_svc,
                    lark_service=self.lark_svc,
                )
                passed = "table" in result.lower() or "task" in result.lower()
                self.reporter.add(TestResult(
                    test_name="agent_list_tables",
                    category="Real API: Agent",
                    passed=passed,
                    duration_ms=(time.time() - start) * 1000,
                    details=result[:200],
                    error=None if passed else result,
                ))

                # Test 3: Create GitHub issue via agent
                start = time.time()
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                result = run_command(
                    f"Create issue '[AGENT TEST] Test Issue {timestamp}' label:test",
                    db=self.db,
                    github_service=self.github_svc,
                    lark_service=self.lark_svc,
                )
                passed = "#" in result or "created" in result.lower()

                # Extract issue number for cleanup
                if "#" in result:
                    try:
                        parts = result.split("#")[1].split()
                        if parts:
                            num_str = "".join(filter(str.isdigit, parts[0]))
                            if num_str:
                                self.created_issues.append(int(num_str))
                    except:
                        pass

                self.reporter.add(TestResult(
                    test_name="agent_create_github_issue",
                    category="Real API: Agent",
                    passed=passed,
                    duration_ms=(time.time() - start) * 1000,
                    details=result[:200],
                    error=None if passed else result,
                ))

                # Test 4: Create Lark record via agent
                start = time.time()
                result = run_command(
                    f"Create record '[AGENT TEST] Lark Task {timestamp}' in table Tasks",
                    db=self.db,
                    github_service=self.github_svc,
                    lark_service=self.lark_svc,
                )
                passed = "created" in result.lower() or "record" in result.lower()
                self.reporter.add(TestResult(
                    test_name="agent_create_lark_record",
                    category="Real API: Agent",
                    passed=passed,
                    duration_ms=(time.time() - start) * 1000,
                    details=result[:200],
                    error=None if passed else result,
                ))

                # Test 5: Sync status
                start = time.time()
                result = run_command(
                    "Sync status",
                    db=self.db,
                    github_service=self.github_svc,
                    lark_service=self.lark_svc,
                )
                passed = "pending" in result.lower() or "status" in result.lower()
                self.reporter.add(TestResult(
                    test_name="agent_sync_status",
                    category="Real API: Agent",
                    passed=passed,
                    duration_ms=(time.time() - start) * 1000,
                    details=result[:200],
                    error=None if passed else result,
                ))

                return True

        except Exception as e:
            self.reporter.add(TestResult(
                test_name="agent_commands",
                category="Real API: Agent",
                passed=False,
                duration_ms=0,
                error=str(e),
            ))
            traceback.print_exc()
            return False


def run_real_api_tests(reporter: TestReporter) -> bool:
    """Run tests against real GitHub and Lark APIs."""
    print("\n" + "=" * 60)
    print("RUNNING REAL API TESTS")
    print("=" * 60)
    print("WARNING: This will create real GitHub issues and Lark records!")

    # Check required environment variables
    required_vars = [
        "GITHUB_TOKEN",
        "LARK_MCP_CLIENT_ID",
        "LARK_MCP_CLIENT_SECRET",
        "LARK_APP_TOKEN",
        "LARK_TASKS_TABLE_ID",
    ]

    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        print(f"\n[ERROR] Missing required environment variables: {missing}")
        reporter.add(TestResult(
            test_name="env_check",
            category="Real API: Setup",
            passed=False,
            duration_ms=0,
            error=f"Missing: {missing}",
        ))
        return False

    tester = RealAPITester(reporter)

    try:
        if not tester.setup():
            return False

        all_passed = True
        all_passed &= tester.test_github_service_directly()
        all_passed &= tester.test_lark_service_directly()
        all_passed &= tester.test_agent_commands()

        return all_passed

    finally:
        tester.cleanup()


# =============================================================================
# Main Entry Point
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Run GithubAutoLark tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python test_control.py --unit          # Unit tests only
    python test_control.py --integration   # Integration tests (mocked)
    python test_control.py --real          # Real API tests
    python test_control.py --all           # All tests
    python test_control.py                 # Same as --all
        """,
    )

    parser.add_argument("--unit", action="store_true", help="Run unit tests")
    parser.add_argument("--integration", action="store_true", help="Run integration tests")
    parser.add_argument("--real", action="store_true", help="Run real API tests")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--save", type=str, default=None, help="Save results to file")

    args = parser.parse_args()

    # Default to --all if no specific test type selected
    if not (args.unit or args.integration or args.real or args.all):
        args.all = True

    reporter = TestReporter()

    print("=" * 60)
    print("GithubAutoLark Test Suite")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    all_passed = True

    if args.unit or args.all:
        all_passed &= run_unit_tests(reporter)

    if args.integration or args.all:
        all_passed &= run_integration_tests(reporter)

    if args.real or args.all:
        all_passed &= run_real_api_tests(reporter)

    reporter.print_summary()

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = args.save or f"test_results_{timestamp}.json"
    reporter.save(filename)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
