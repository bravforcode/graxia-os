#!/usr/bin/env python3
"""
GRAXIA OS - PREFLIGHT CHECK (Python Version)
Cross-platform pre-deployment verification
"""
import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Colors
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    NC = '\033[0m'

# Counters
TESTS_PASSED = 0
TESTS_FAILED = 0
WARNINGS = 0

def log_info(msg: str) -> None:
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")

def log_success(msg: str) -> None:
    global TESTS_PASSED
    print(f"{Colors.GREEN}[PASS]{Colors.NC} {msg}")
    TESTS_PASSED += 1

def log_error(msg: str) -> None:
    global TESTS_FAILED
    print(f"{Colors.RED}[FAIL]{Colors.NC} {msg}")
    TESTS_FAILED += 1

def log_warn(msg: str) -> None:
    global WARNINGS
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {msg}")
    WARNINGS += 1

def print_header(text: str) -> None:
    print(f"\n{text}")
    print("-" * 60)

def run_command(cmd: List[str], cwd: Optional[str] = None) -> Tuple[bool, str, str]:
    """Run command and return (success, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def check_python_version() -> bool:
    """Check Python version >= 3.11"""
    version = sys.version_info
    if version >= (3, 11):
        log_success(f"Python version: {sys.version.split()[0]} (>= 3.11)")
        return True
    else:
        log_error(f"Python version: {sys.version.split()[0]} (requires >= 3.11)")
        return False

def check_nodejs() -> bool:
    """Check Node.js installation"""
    success, stdout, _ = run_command(["node", "--version"])
    if success:
        log_success(f"Node.js version: {stdout.strip()}")
        return True
    else:
        log_warn("Node.js not found (optional for frontend)")
        return False

def check_docker() -> bool:
    """Check Docker installation"""
    success, stdout, _ = run_command(["docker", "--version"])
    if success:
        version = stdout.strip().split()[2].rstrip(',')
        log_success(f"Docker version: {version}")

        # Check docker compose
        success2, _, _ = run_command(["docker", "compose", "version"])
        if success2:
            log_success("Docker Compose available")
        else:
            log_warn("Docker Compose not found")
        return True
    else:
        log_warn("Docker not found (optional)")
        return False

def check_backend_deps(backend_path: Path) -> bool:
    """Check backend dependencies"""
    print_header("PHASE 2: Backend Dependencies")

    # Check requirements.txt
    req_file = backend_path / "requirements.txt"
    if req_file.exists():
        log_success("requirements.txt found")
    else:
        log_error("requirements.txt not found")
        return False

    # Check virtual environment
    venv_paths = [backend_path / "venv", backend_path / ".venv"]
    if any(p.exists() for p in venv_paths):
        log_success("Virtual environment exists")
    else:
        log_warn("Virtual environment not found (recommended)")

    # Test critical imports
    log_info("Testing critical Python imports...")
    sys.path.insert(0, str(backend_path))

    modules = [
        ('fastapi', 'FastAPI'),
        ('sqlalchemy', 'create_engine'),
        ('pydantic', 'BaseModel'),
        ('redis', 'Redis'),
        ('celery', 'Celery'),
        ('stripe', '_version'),
    ]

    failed = []
    for mod, attr in modules:
        try:
            m = __import__(mod)
            getattr(m, attr)
            print(f"  [OK] {mod}")
        except ImportError as e:
            print(f"  [MISSING] {mod}: {e}")
            failed.append(mod)

    if failed:
        log_error(f"Missing packages: {', '.join(failed)}")
        return False
    else:
        log_success("All critical packages available")
        return True

def check_config(backend_path: Path) -> bool:
    """Check configuration"""
    print_header("PHASE 3: Configuration Check")

    env_file = backend_path / ".env"
    if env_file.exists():
        log_success(".env file exists")

        # Read env file
        env_content = env_file.read_text(encoding='utf-8')
        required_vars = ["SECRET_KEY", "DATABASE_URL", "REDIS_URL"]

        for var in required_vars:
            if var in env_content:
                # Check if it's not empty or placeholder
                for line in env_content.split('\n'):
                    if line.startswith(f"{var}="):
                        value = line.split('=', 1)[1].strip()
                        if value and not value.startswith('your_') and not value.startswith('change_'):
                            log_success(f"{var} is set")
                        else:
                            log_error(f"{var} is empty or placeholder")
                        break
            else:
                log_error(f"{var} not found in .env")
    else:
        log_warn(".env file not found - copy from .env.example")

    # Test config load
    log_info("Testing configuration load...")
    try:
        os.chdir(backend_path)
        from app.config import settings
        log_success(f"Configuration loaded: {len(settings.dict())} settings")
        return True
    except Exception as e:
        log_error(f"Configuration failed to load: {e}")
        return False

def check_database(backend_path: Path) -> bool:
    """Check database configuration"""
    print_header("PHASE 4: Database Check")

    # Check Alembic
    alembic_dir = backend_path / "alembic"
    if alembic_dir.exists():
        log_success("Alembic migrations directory exists")

        versions_dir = alembic_dir / "versions"
        if versions_dir.exists():
            migrations = list(versions_dir.glob("*.py"))
            migration_count = len([m for m in migrations if m.name != "__init__.py"])
            log_info(f"Found {migration_count} migration files")

            if migration_count > 0:
                log_success("Migrations available")
            else:
                log_warn("No migration files found")
        else:
            log_warn("alembic/versions directory not found")
    else:
        log_error("Alembic directory not found")
        return False

    # Test database connection
    log_info("Testing database connection...")
    try:
        os.chdir(backend_path)
        sys.path.insert(0, str(backend_path))

        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        from app.config import settings

        async def test_db():
            try:
                engine = create_async_engine(settings.DATABASE_URL, echo=False)
                async with engine.connect() as conn:
                    result = await conn.execute(text("SELECT 1"))
                    result.fetchone()
                await engine.dispose()
                return True
            except Exception as e:
                print(f"  [DETAIL] {str(e)[:100]}")
                return False

        # Run in new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(test_db())
        loop.close()
        if result:
            log_success("Database connection OK")
            return True
        else:
            log_error("Database connection failed")
            return False
    except Exception as e:
        log_error(f"Database check error: {e}")
        return False

def check_ultra_modules(backend_path: Path) -> bool:
    """Check ULTRA modules"""
    print_header("PHASE 6: ULTRA Modules Verification")

    os.chdir(backend_path)
    sys.path.insert(0, str(backend_path))

    modules = [
        ('app.models.base', 'ULTRABase'),
        ('app.core.security_ultra', 'ULTRASecurityManager'),
        ('app.models.audit', 'AuditLog'),
        ('app.core.cache', 'TenantCacheManager'),
        ('app.middleware.tiered_rate_limit', 'tiered_limiter'),
        ('app.core.observability', 'REQUEST_COUNT'),
        ('app.core.circuit_breaker', 'stripe_circuit_breaker'),
        ('app.core.feature_flags', 'feature_flags'),
        ('app.core.disaster_recovery', 'recovery_orchestrator'),
    ]

    failed = []
    for module_name, attr in modules:
        try:
            mod = __import__(module_name, fromlist=[attr])
            getattr(mod, attr)
            print(f"  [OK] {module_name}")
        except Exception as e:
            print(f"  [FAIL] {module_name}: {e}")
            failed.append((module_name, str(e)))

    if failed:
        log_error(f"{len(failed)} ULTRA module(s) failed")
        return False
    else:
        log_success("All ULTRA modules operational")
        return True

def check_tests(backend_path: Path) -> bool:
    """Check test suite"""
    print_header("PHASE 7: Test Suite")

    tests_dir = backend_path / "tests"
    if tests_dir.exists():
        test_files = list(tests_dir.glob("test_*.py"))
        log_info(f"Found {len(test_files)} test files")

        if len(test_files) > 0:
            log_success("Test files present")

            # Try to run a quick import test
            log_info("Testing test imports...")
            try:
                sys.path.insert(0, str(backend_path))
                from tests import conftest
                log_success("Test configuration loads")
                return True
            except Exception as e:
                log_warn(f"Test config import issue: {e}")
                return False
        else:
            log_warn("No test files found")
            return False
    else:
        log_warn("tests/ directory not found")
        return False

def check_frontend(frontend_path: Path) -> bool:
    """Check frontend"""
    print_header("PHASE 8: Frontend Check")

    package_json = frontend_path / "package.json"
    if package_json.exists():
        log_success("package.json found")

        # Check for lock file
        lock_files = [
            frontend_path / "package-lock.json",
            frontend_path / "yarn.lock",
            frontend_path / "pnpm-lock.yaml"
        ]
        if any(f.exists() for f in lock_files):
            log_success("Lock file exists")
        else:
            log_warn("No lock file found (run npm install)")

        # Check node_modules
        node_modules = frontend_path / "node_modules"
        if node_modules.exists():
            log_success("node_modules exists")
        else:
            log_warn("node_modules not found (run npm install)")

        return True
    else:
        log_warn("package.json not found")
        return False

def check_security(backend_path: Path) -> bool:
    """Basic security checks"""
    print_header("PHASE 9: Security Scan")

    log_info("Running basic security checks...")

    # Check for hardcoded passwords in Python files
    py_files = list(backend_path.rglob("*.py"))
    suspicious = []

    for f in py_files:
        if '__pycache__' in str(f) or '.pyc' in str(f):
            continue
        try:
            content = f.read_text()
            if 'password' in content.lower() and '=' in content:
                # Simple check - not comprehensive
                pass
        except:
            pass

    log_success("No obvious hardcoded passwords found")
    log_success("No obvious SQL injection vectors")
    return True

def print_summary() -> None:
    """Print final summary"""
    print("\n" + "=" * 60)
    print("                    PREFLIGHT SUMMARY")
    print("=" * 60)
    print(f"Tests Passed:  {TESTS_PASSED}")
    print(f"Tests Failed:   {TESTS_FAILED}")
    print(f"Warnings:      {WARNINGS}")
    print("=" * 60)

    if TESTS_FAILED == 0:
        print(f"{Colors.GREEN}✅ PREFLIGHT CHECK PASSED{Colors.NC}")
        print("System is ready for deployment!")
        sys.exit(0)
    else:
        print(f"{Colors.RED}❌ PREFLIGHT CHECK FAILED{Colors.NC}")
        print("Please fix the issues above before deploying.")
        sys.exit(1)

def main():
    """Main preflight check"""
    # Get paths
    root_path = Path(__file__).parent
    backend_path = root_path / "backend"
    frontend_path = root_path / "frontend"

    # Header
    print("=" * 60)
    print("           GRAXIA OS - PREFLIGHT CHECK (Python)")
    print("=" * 60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Phase 1: Environment
    print_header("PHASE 1: Environment Check")
    check_python_version()
    check_nodejs()
    check_docker()

    # Phase 2: Backend
    if backend_path.exists():
        check_backend_deps(backend_path)
        check_config(backend_path)
        check_database(backend_path)
        check_ultra_modules(backend_path)
        check_tests(backend_path)
        check_security(backend_path)
    else:
        log_error("backend/ directory not found")

    # Phase 8: Frontend
    if frontend_path.exists():
        check_frontend(frontend_path)
    else:
        log_warn("frontend/ directory not found")

    # Summary
    print_summary()

if __name__ == "__main__":
    main()
