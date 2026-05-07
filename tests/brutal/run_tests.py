#!/usr/bin/env python3
"""
BRUTAL MODE Test Runner
Execute comprehensive test suite with detailed reporting
"""
import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TestResult:
    """Test execution result"""
    name: str
    status: str  # passed, failed, skipped, error
    duration: float
    message: str = ""
    stdout: str = ""
    stderr: str = ""


@dataclass
class TestSuiteReport:
    """Complete test suite report"""
    timestamp: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    coverage: float = 0.0
    results: list[TestResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def run_pytest_with_report(
    markers: list[str] = None,
    verbose: bool = True,
    fail_fast: bool = False,
    coverage: bool = True,
) -> TestSuiteReport:
    """
    Run pytest and generate detailed report.
    
    Args:
        markers: pytest markers to filter (e.g., ["unit", "version"])
        verbose: Enable verbose output
        fail_fast: Stop on first failure
        coverage: Enable coverage reporting
    
    Returns:
        TestSuiteReport with complete results
    """
    report = TestSuiteReport(
        timestamp=datetime.utcnow().isoformat(),
    )
    
    # Build pytest command
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/brutal/test_core_skills_features_1_10.py",
        "-v" if verbose else "",
        "--tb=short",
        "--strict-markers",
        "-x" if fail_fast else "",
    ]
    
    # Add markers
    if markers:
        marker_expr = " and ".join(markers)
        cmd.extend(["-m", marker_expr])
    
    # Add coverage
    if coverage:
        cmd.extend([
            "--cov=backend.app.services",
            "--cov=backend.app.api",
            "--cov=backend.app.models",
            "--cov-report=term-missing",
            "--cov-report=json:.coverage/coverage.json",
            "--cov-report=html:.coverage/html",
        ])
    
    # Remove empty strings
    cmd = [c for c in cmd if c]
    
    print(f"🧪 Running: {' '.join(cmd)}")
    print("=" * 80)
    
    start_time = time.time()
    
    # Run pytest
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent,
    )
    
    report.duration = time.time() - start_time
    
    # Parse output
    stdout_lines = result.stdout.split('\n')
    
    for line in stdout_lines:
        # Parse test results
        if '::' in line and ('PASSED' in line or 'FAILED' in line or 'SKIPPED' in line):
            parts = line.split()
            test_name = [p for p in parts if '::' in p][0] if parts else "unknown"
            
            if 'PASSED' in line:
                report.passed += 1
                report.results.append(TestResult(
                    name=test_name, status="passed", duration=0.0
                ))
            elif 'FAILED' in line:
                report.failed += 1
                report.failures.append(test_name)
                report.results.append(TestResult(
                    name=test_name, status="failed", duration=0.0
                ))
            elif 'SKIPPED' in line:
                report.skipped += 1
                report.results.append(TestResult(
                    name=test_name, status="skipped", duration=0.0
                ))
    
    # Parse summary line
    for line in reversed(stdout_lines):
        if 'passed' in line or 'failed' in line or 'error' in line:
            # Extract counts
            import re
            passed_match = re.search(r'(\d+) passed', line)
            failed_match = re.search(r'(\d+) failed', line)
            skipped_match = re.search(r'(\d+) skipped', line)
            error_match = re.search(r'(\d+) error', line)
            
            if passed_match:
                report.passed = int(passed_match.group(1))
            if failed_match:
                report.failed = int(failed_match.group(1))
            if skipped_match:
                report.skipped = int(skipped_match.group(1))
            if error_match:
                report.errors = int(error_match.group(1))
            
            break
    
    report.total_tests = report.passed + report.failed + report.skipped + report.errors
    
    # Parse coverage
    if coverage:
        try:
            coverage_file = Path(".coverage/coverage.json")
            if coverage_file.exists():
                with open(coverage_file) as f:
                    cov_data = json.load(f)
                    report.coverage = cov_data.get("totals", {}).get("percent_covered", 0.0)
        except Exception as e:
            print(f"⚠️  Could not parse coverage: {e}")
    
    return report


def print_report(report: TestSuiteReport) -> None:
    """Print formatted test report."""
    print("\n" + "=" * 80)
    print("📊 BRUTAL MODE TEST REPORT")
    print("=" * 80)
    print(f"Timestamp: {report.timestamp}")
    print(f"Duration: {report.duration:.2f}s")
    print("-" * 80)
    
    print(f"\n📈 Summary:")
    print(f"   Total Tests: {report.total_tests}")
    print(f"   ✅ Passed:   {report.passed}")
    print(f"   ❌ Failed:   {report.failed}")
    print(f"   ⏭️  Skipped:  {report.skipped}")
    print(f"   ⚠️  Errors:   {report.errors}")
    
    if report.coverage > 0:
        print(f"\n📊 Coverage: {report.coverage:.2f}%")
        if report.coverage >= 90:
            print("   ✅ Coverage target met (90%+)")
        else:
            print("   ⚠️  Coverage below target (90%)")
    
    if report.failures:
        print(f"\n❌ Failures ({len(report.failures)}):")
        for failure in report.failures:
            print(f"   • {failure}")
    
    # Success criteria
    print("\n" + "=" * 80)
    if report.failed == 0 and report.errors == 0:
        if report.coverage >= 90:
            print("✅ BRUTAL MODE: ALL TESTS PASSED, COVERAGE MET")
        else:
            print("⚠️  BRUTAL MODE: TESTS PASSED, COVERAGE BELOW 90%")
    else:
        print("❌ BRUTAL MODE: TESTS FAILED - FIX REQUIRED")
    print("=" * 80)


def run_feature_tests(feature: str) -> TestSuiteReport:
    """Run tests for specific feature."""
    feature_markers = {
        "1": ["version"],
        "2": ["fork"],
        "3": ["merge"],
        "4": ["dependency"],
        "5": ["template"],
        "6": ["validation"],
        "7": ["testing"],
        "8": ["abtest"],
        "9": ["rollback"],
        "10": ["draft"],
    }
    
    markers = feature_markers.get(feature, [])
    if not markers:
        print(f"⚠️  Unknown feature: {feature}")
        return TestSuiteReport(timestamp=datetime.utcnow().isoformat())
    
    return run_pytest_with_report(
        markers=markers,
        verbose=True,
        fail_fast=True,
        coverage=True,
    )


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="BRUTAL MODE Test Runner for Core Skills Features 1-10"
    )
    parser.add_argument(
        "--feature",
        type=str,
        choices=[str(i) for i in range(1, 11)],
        help="Run tests for specific feature (1-10)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all tests",
    )
    parser.add_argument(
        "--unit",
        action="store_true",
        help="Run unit tests only",
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run integration tests only",
    )
    parser.add_argument(
        "--e2e",
        action="store_true",
        help="Run E2E tests only",
    )
    parser.add_argument(
        "--performance",
        action="store_true",
        help="Run performance tests only",
    )
    parser.add_argument(
        "--security",
        action="store_true",
        help="Run security tests only",
    )
    parser.add_argument(
        "--brutal",
        action="store_true",
        help="Run all tests with brutal mode (strict)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first failure",
    )
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Skip coverage reporting",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Save report to JSON file",
    )
    
    args = parser.parse_args()
    
    # Determine test markers
    markers = []
    
    if args.feature:
        report = run_feature_tests(args.feature)
    elif args.unit:
        report = run_pytest_with_report(markers=["unit"], fail_fast=args.fail_fast)
    elif args.integration:
        report = run_pytest_with_report(markers=["integration"], fail_fast=args.fail_fast)
    elif args.e2e:
        report = run_pytest_with_report(markers=["e2e"], fail_fast=args.fail_fast)
    elif args.performance:
        report = run_pytest_with_report(markers=["performance"], fail_fast=args.fail_fast)
    elif args.security:
        report = run_pytest_with_report(markers=["security"], fail_fast=args.fail_fast)
    elif args.brutal or args.all:
        report = run_pytest_with_report(
            markers=["brutal"],
            fail_fast=args.fail_fast,
            coverage=not args.no_coverage,
        )
    else:
        # Default: run unit and integration tests
        report = run_pytest_with_report(
            markers=["unit", "integration"],
            fail_fast=args.fail_fast,
        )
    
    # Print report
    print_report(report)
    
    # Save to file if requested
    if args.output:
        report_dict = {
            "timestamp": report.timestamp,
            "duration": report.duration,
            "total_tests": report.total_tests,
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
            "errors": report.errors,
            "coverage": report.coverage,
            "failures": report.failures,
        }
        with open(args.output, 'w') as f:
            json.dump(report_dict, f, indent=2)
        print(f"\n📝 Report saved to: {args.output}")
    
    # Exit code
    return 0 if report.failed == 0 and report.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
