"""
CI Security Check — runs independently of local git hooks.
Can be called from CI pipelines, manual runs, or pre-push hooks.
Exits non-zero if findings detected.
"""
import sys
import os
import subprocess
import re

# ── Configuration ──
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
SCAN_PATTERNS = {
    "password_assignment": re.compile(r'(?:password|passwd|pwd)\s*[:=]\s*["\'][^"\'\s]{4,}', re.IGNORECASE),
    "api_key_assignment": re.compile(r'(?:api_key|apikey|api\.key)\s*[:=]\s*["\'][^"\'\s]{8,}', re.IGNORECASE),
    "secret_assignment": re.compile(r'(?:secret|token|credential)\s*[:=]\s*["\'][^"\'\s]{8,}', re.IGNORECASE),
    "mt5_credential_env": re.compile(r'(?:MT5_LOGIN|MT5_PASSWORD|MT5_SERVER)\s*='),
}

FORBIDDEN_ORDER_IMPORTS = [
    "order_send",
    "TRADE_ACTION_DEAL",
    "TRADE_ACTION_PENDING",
    "TRADE_ACTION_REMOVE",
    "TRADE_ACTION_SLTP",
    "TRADE_ACTION_MODIFY",
]

SELF_SKIP = os.path.basename(__file__)

ALLOWED_ORDER_FILES = [
    "execution/demo_canary/order_submission.py",
]

def scan_file_for_secrets(filepath: str) -> list:
    """Scan a single file for credential patterns."""
    findings = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        for pattern_name, pattern in SCAN_PATTERNS.items():
            for match in pattern.finditer(content):
                line_num = content[:match.start()].count('\n') + 1
                findings.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": pattern_name,
                    "match": match.group()[:40] + "..." if len(match.group()) > 40 else match.group(),
                })
    except Exception as e:
        findings.append({"file": filepath, "error": str(e)})
    return findings

def scan_forbidden_order_imports() -> list:
    """Scan for order_send and TRADE_ACTION outside allowlisted files."""
    findings = []
    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip .git, __pycache__, venv, node_modules
        if '.git' in dirs: dirs.remove('.git')
        if '__pycache__' in dirs: dirs.remove('__pycache__')
        if 'venv' in dirs: dirs.remove('venv')
        if 'node_modules' in dirs: dirs.remove('node_modules')
        
        for fname in files:
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, REPO_ROOT)
            
            # Skip self and allowlisted files
            if fname == SELF_SKIP:
                continue
            if any(relpath.endswith(allowed) for allowed in ALLOWED_ORDER_FILES):
                continue
            
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                for imp in FORBIDDEN_ORDER_IMPORTS:
                    if imp in content:
                        for i, line in enumerate(content.split('\n'), 1):
                            if imp in line:
                                findings.append({
                                    "file": relpath,
                                    "line": i,
                                    "forbidden_import": imp,
                                    "context": line.strip()[:80],
                                })
            except Exception:
                pass
    
    return findings

def main():
    findings = []
    print("=" * 60)
    print("CI SECURITY CHECK")
    print("=" * 60)
    
    # Secret scan
    print("\n[1/3] Scanning for secrets...")
    for root, dirs, files in os.walk(REPO_ROOT):
        if '.git' in dirs: dirs.remove('.git')
        if '__pycache__' in dirs: dirs.remove('__pycache__')
        if 'venv' in dirs: dirs.remove('venv')
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in ('.py', '.yaml', '.yml', '.json', '.toml', '.ini', '.env', '.md', '.txt'):
                fpath = os.path.join(root, fname)
                findings.extend(scan_file_for_secrets(fpath))
    
    if findings:
        print(f"  WARNING: {len(findings)} potential secret(s) found:")
        for f in findings[:10]:
            print(f"    {f['file']}:{f.get('line', '?')} [{f.get('pattern', 'error')}] {f.get('match', f.get('error', ''))}")
    else:
        print("  CLEAN — no secrets detected")
    
    # Forbidden import scan
    print("\n[2/3] Scanning for forbidden order API imports...")
    import_findings = scan_forbidden_order_imports()
    if import_findings:
        print(f"  WARNING: {len(import_findings)} forbidden import(s) outside allowlist:")
        for f in import_findings:
            print(f"    {f['file']}:{f['line']} — {f['forbidden_import']}")
        findings.extend(import_findings)
    else:
        print("  CLEAN — all order_send/TRADE_ACTION confined to allowlist")
    
    # Summary
    print(f"\n[3/3] Summary")
    print(f"  Total findings: {len(findings)}")
    
    if findings:
        print("\n  [FAIL] - findings detected")
        sys.exit(1)
    else:
        print("\n  [PASS] - security check clean")
        sys.exit(0)

if __name__ == "__main__":
    main()
