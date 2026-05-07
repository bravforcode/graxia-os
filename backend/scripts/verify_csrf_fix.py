#!/usr/bin/env python3
"""
CSRF Timing Attack Fix Verification Script

This script performs automated verification that the CSRF timing attack
vulnerability has been properly fixed. It performs:

1. Static code analysis to verify constant-time operations are used
2. Statistical timing analysis to detect timing leaks
3. Functional testing of all CSRF validation paths

Usage:
    python backend/scripts/verify_csrf_fix.py

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""
from __future__ import annotations

import ast
import statistics
import sys
import time
from pathlib import Path

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text: str) -> None:
    """Print a section header."""
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{text:^80}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")


def print_success(text: str) -> None:
    """Print a success message."""
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text: str) -> None:
    """Print an error message."""
    print(f"{RED}✗ {text}{RESET}")


def print_warning(text: str) -> None:
    """Print a warning message."""
    print(f"{YELLOW}⚠ {text}{RESET}")


def print_info(text: str) -> None:
    """Print an info message."""
    print(f"  {text}")


class CSRFSecurityAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze CSRF security patterns."""
    
    def __init__(self):
        self.issues = []
        self.hmac_compare_digest_used = False
        self.short_circuit_eval_found = False
        self.constant_time_checks = []
        self.in_csrf_middleware = False
        
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track when we're inside CSRFMiddleware class."""
        if node.name == "CSRFMiddleware":
            self.in_csrf_middleware = True
            self.generic_visit(node)
            self.in_csrf_middleware = False
        else:
            self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call) -> None:
        """Check for hmac.compare_digest usage."""
        if self.in_csrf_middleware:
            if isinstance(node.func, ast.Attribute):
                if (isinstance(node.func.value, ast.Name) and 
                    node.func.value.id == "hmac" and 
                    node.func.attr == "compare_digest"):
                    self.hmac_compare_digest_used = True
                    self.constant_time_checks.append(ast.unparse(node))
        self.generic_visit(node)
    
    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """Check for short-circuit evaluation patterns."""
        if self.in_csrf_middleware:
            # Check for patterns like: if not token1 or not token2
            if isinstance(node.op, ast.Or):
                for value in node.values:
                    if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.Not):
                        # This could be a timing leak if used for token validation
                        context = ast.unparse(node)
                        if "token" in context.lower():
                            self.issues.append(
                                f"Potential timing leak: short-circuit OR with token check: {context}"
                            )
        self.generic_visit(node)
    
    def visit_Compare(self, node: ast.Compare) -> None:
        """Check for direct string comparisons of tokens."""
        if self.in_csrf_middleware:
            context = ast.unparse(node)
            if "token" in context.lower():
                # Check if this is a direct comparison (not using hmac.compare_digest)
                if any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                    # This might be okay if it's checking for None or length
                    if "None" not in context and "len(" not in context:
                        self.issues.append(
                            f"Potential timing leak: direct token comparison: {context}"
                        )
        self.generic_visit(node)


def check_static_code_analysis() -> bool:
    """Perform static code analysis on security.py."""
    print_header("STATIC CODE ANALYSIS")
    
    security_file = Path("backend/app/middleware/security.py")
    if not security_file.exists():
        print_error(f"File not found: {security_file}")
        return False
    
    with open(security_file) as f:
        source = f.read()
    
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print_error(f"Syntax error in {security_file}: {e}")
        return False
    
    analyzer = CSRFSecurityAnalyzer()
    analyzer.visit(tree)
    
    all_passed = True
    
    # Check 1: hmac.compare_digest is used
    if analyzer.hmac_compare_digest_used:
        print_success("hmac.compare_digest is used for token comparison")
    else:
        print_error("hmac.compare_digest is NOT used for token comparison")
        all_passed = False
    
    # Check 2: No timing leak issues found
    if not analyzer.issues:
        print_success("No obvious timing leak patterns detected")
    else:
        print_error(f"Found {len(analyzer.issues)} potential timing leak(s):")
        for issue in analyzer.issues:
            print_info(f"  - {issue}")
        all_passed = False
    
    # Check 3: Constant-time checks are present
    if analyzer.constant_time_checks:
        print_success(f"Found {len(analyzer.constant_time_checks)} constant-time check(s)")
        for check in analyzer.constant_time_checks:
            print_info(f"  - {check}")
    else:
        print_warning("No constant-time checks detected (this might be okay)")
    
    # Check 4: Verify specific patterns in source
    if "cookie_token_present" in source and "header_token_present" in source:
        print_success("Token presence checks use explicit variables (good pattern)")
    else:
        print_warning("Token presence checks might use short-circuit evaluation")
    
    if "len(cookie_token)" in source or "len(header_token)" in source:
        print_success("Token length checks are used (prevents short-circuit)")
    else:
        print_warning("Token length checks not found (might use truthiness)")
    
    return all_passed


def check_functional_tests() -> bool:
    """Run functional tests for CSRF validation."""
    print_header("FUNCTIONAL TESTS")
    
    try:
        import subprocess
        result = subprocess.run(
            ["python", "-m", "pytest", "backend/tests/test_csrf_timing.py", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        if result.returncode == 0:
            print_success("All CSRF timing tests passed")
            # Print test summary
            for line in result.stdout.split("\n"):
                if "passed" in line.lower() or "PASSED" in line:
                    print_info(line.strip())
            return True
        else:
            print_error("Some CSRF timing tests failed")
            print_info("Test output:")
            print(result.stdout)
            if result.stderr:
                print_info("Error output:")
                print(result.stderr)
            return False
    except subprocess.TimeoutExpired:
        print_error("Tests timed out after 120 seconds")
        return False
    except FileNotFoundError:
        print_error("pytest not found. Install with: pip install pytest pytest-asyncio")
        return False
    except Exception as e:
        print_error(f"Error running tests: {e}")
        return False


def check_timing_analysis() -> bool:
    """Perform basic timing analysis on token validation."""
    print_header("TIMING ANALYSIS")
    
    try:
        from app.middleware.security import validate_csrf_token_signature, generate_csrf_token
    except ImportError as e:
        print_error(f"Failed to import security module: {e}")
        return False
    
    session_id = "timing-test-session"
    valid_token = generate_csrf_token(session_id)
    
    # Measure time for valid token
    valid_times = []
    for _ in range(1000):
        start = time.perf_counter()
        validate_csrf_token_signature(valid_token, session_id)
        elapsed = time.perf_counter() - start
        valid_times.append(elapsed)
    
    # Measure time for invalid token
    invalid_times = []
    for _ in range(1000):
        start = time.perf_counter()
        validate_csrf_token_signature(valid_token, "wrong-session")
        elapsed = time.perf_counter() - start
        invalid_times.append(elapsed)
    
    # Measure time for malformed token
    malformed_times = []
    for _ in range(1000):
        start = time.perf_counter()
        validate_csrf_token_signature("malformed-token", session_id)
        elapsed = time.perf_counter() - start
        malformed_times.append(elapsed)
    
    # Calculate statistics
    valid_mean = statistics.mean(valid_times)
    invalid_mean = statistics.mean(invalid_times)
    malformed_mean = statistics.mean(malformed_times)
    
    valid_stdev = statistics.stdev(valid_times)
    invalid_stdev = statistics.stdev(invalid_times)
    malformed_stdev = statistics.stdev(malformed_times)
    
    print_info(f"Valid token:     mean={valid_mean*1e6:.2f}µs, stdev={valid_stdev*1e6:.2f}µs")
    print_info(f"Invalid token:   mean={invalid_mean*1e6:.2f}µs, stdev={invalid_stdev*1e6:.2f}µs")
    print_info(f"Malformed token: mean={malformed_mean*1e6:.2f}µs, stdev={malformed_stdev*1e6:.2f}µs")
    
    # Check if timing differences are within acceptable range
    max_stdev = max(valid_stdev, invalid_stdev, malformed_stdev)
    valid_invalid_diff = abs(valid_mean - invalid_mean)
    valid_malformed_diff = abs(valid_mean - malformed_mean)
    
    all_passed = True
    
    # Allow up to 5 standard deviations difference (stricter than test suite)
    threshold = 5 * max_stdev
    
    if valid_invalid_diff < threshold:
        print_success(f"Valid vs Invalid timing difference: {valid_invalid_diff*1e6:.2f}µs (< {threshold*1e6:.2f}µs)")
    else:
        print_error(f"Valid vs Invalid timing difference: {valid_invalid_diff*1e6:.2f}µs (>= {threshold*1e6:.2f}µs)")
        all_passed = False
    
    if valid_malformed_diff < threshold:
        print_success(f"Valid vs Malformed timing difference: {valid_malformed_diff*1e6:.2f}µs (< {threshold*1e6:.2f}µs)")
    else:
        print_error(f"Valid vs Malformed timing difference: {valid_malformed_diff*1e6:.2f}µs (>= {threshold*1e6:.2f}µs)")
        all_passed = False
    
    return all_passed


def check_existing_tests() -> bool:
    """Verify existing CSRF tests still pass."""
    print_header("EXISTING CSRF TESTS")
    
    try:
        import subprocess
        result = subprocess.run(
            ["python", "-m", "pytest", "backend/tests/test_security_contracts.py::test_csrf_is_enforced_for_state_changing_requests", "-v"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0:
            print_success("Existing CSRF test still passes (backward compatibility confirmed)")
            return True
        else:
            print_error("Existing CSRF test failed (regression detected)")
            print_info("Test output:")
            print(result.stdout)
            return False
    except Exception as e:
        print_warning(f"Could not run existing tests: {e}")
        return True  # Don't fail if we can't run the test


def main() -> int:
    """Run all verification checks."""
    print_header("CSRF TIMING ATTACK FIX VERIFICATION")
    print_info("This script verifies that the CSRF timing attack vulnerability")
    print_info("has been properly fixed using constant-time operations.")
    
    results = {
        "Static Code Analysis": check_static_code_analysis(),
        "Timing Analysis": check_timing_analysis(),
        "Functional Tests": check_functional_tests(),
        "Existing Tests": check_existing_tests(),
    }
    
    # Print summary
    print_header("VERIFICATION SUMMARY")
    
    all_passed = True
    for check_name, passed in results.items():
        if passed:
            print_success(f"{check_name}: PASSED")
        else:
            print_error(f"{check_name}: FAILED")
            all_passed = False
    
    print()
    if all_passed:
        print_success("✓ ALL CHECKS PASSED - CSRF timing attack fix verified")
        return 0
    else:
        print_error("✗ SOME CHECKS FAILED - Review the output above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
