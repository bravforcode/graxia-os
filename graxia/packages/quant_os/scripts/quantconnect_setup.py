"""
QuantConnect Setup — Configure QuantConnect credentials for LEAN CLI.

Usage:
    python scripts/quantconnect_setup.py --user-id <id> --api-token <token>

Prerequisites:
    1. Install LEAN CLI: pip install lean
    2. Create QuantConnect account: https://www.quantconnect.com/signup
    3. Get API token: https://www.quantconnect.com/account
"""
import argparse
import subprocess
import sys


def setup_credentials(user_id: str, api_token: str):
    """Setup QuantConnect credentials for LEAN CLI."""
    print(f"Setting up QuantConnect credentials...")
    print(f"  User ID: {user_id}")
    print(f"  API Token: {api_token[:8]}...")
    print()

    # Set credentials using LEAN CLI
    commands = [
        ["lean", "config", "set", "job-user-id", user_id],
        ["lean", "config", "set", "api-token", api_token],
    ]

    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error setting config: {result.stderr}")
            return False

    print("Credentials configured successfully!")
    return True


def verify_setup():
    """Verify QuantConnect setup."""
    print("Verifying QuantConnect setup...")

    # Check LEAN CLI version
    result = subprocess.run(["lean", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: LEAN CLI not installed")
        return False

    print(f"  LEAN CLI version: {result.stdout.strip()}")

    # Check credentials
    result = subprocess.run(["lean", "config", "get", "job-user-id"], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        print(f"  Warning: job-user-id not configured")
    else:
        print(f"  job-user-id: {result.stdout.strip()}")

    result = subprocess.run(["lean", "config", "get", "api-token"], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        print(f"  Warning: api-token not configured")
    else:
        print(f"  api-token: {result.stdout.strip()[:8]}...")

    return True


def create_project(name: str):
    """Create a new QuantConnect project."""
    print(f"Creating project: {name}")

    result = subprocess.run(
        ["lean", "project", "create", name, "Python"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Error creating project: {result.stderr}")
        return None

    print(f"Project created successfully!")
    print(f"Output: {result.stdout}")

    # Parse project ID from output
    # LEAN CLI output format may vary
    return None


def main():
    parser = argparse.ArgumentParser(description="QuantConnect Setup")
    parser.add_argument("--user-id", type=str, help="QuantConnect user ID")
    parser.add_argument("--api-token", type=str, help="QuantConnect API token")
    parser.add_argument("--verify", action="store_true", help="Verify setup only")
    parser.add_argument("--create-project", type=str, help="Create a new project")

    args = parser.parse_args()

    if args.verify:
        success = verify_setup()
    elif args.user_id and args.api_token:
        success = setup_credentials(args.user_id, args.api_token)
    elif args.create_project:
        project_id = create_project(args.create_project)
        success = project_id is not None
    else:
        print("Error: Please provide --user-id and --api-token, or --verify, or --create-project")
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
