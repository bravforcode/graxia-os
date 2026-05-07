#!/usr/bin/env python3
"""
Test runner for Quant OS
Run all tests and display summary
"""

import subprocess
import sys


def run_tests():
    """Run all Quant OS tests"""
    print("=" * 70)
    print("Quant OS Test Suite")
    print("=" * 70)
    print()
    
    # Run tests
    result = subprocess.run(
        ["python", "-m", "pytest", "graxia/packages/quant_os/tests/", "-v", "--tb=short"],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    # Parse results
    if "passed" in result.stdout:
        lines = result.stdout.split("\n")
        for line in lines:
            if "passed" in line and "failed" not in line.lower():
                print()
                print("=" * 70)
                print("All tests passed!")
                print("=" * 70)
                return 0
            elif "failed" in line:
                print()
                print("=" * 70)
                print("Some tests failed!")
                print("=" * 70)
                return 1
    
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())
