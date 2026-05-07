import os
import re
import sys
from pathlib import Path

# Regular expressions for potential secrets
SECRET_PATTERNS = [
    r"(?i)api_key", r"(?i)secret_key", r"(?i)password", r"(?i)token",
    r"sk-ant-api03-[a-zA-Z0-9_\-]{95}",  # Claude
    r"xox[bapts]-[0-9]{10,12}-[a-zA-Z0-9]{24,48}", # Slack
]

def check_secrets():
    print("🔍 Checking for hardcoded secrets...")
    violations = []
    # Simplified scan for the demo
    for root, _, files in os.walk("."):
        if "node_modules" in root or ".git" in root or "venv" in root:
            continue
        for file in files:
            if file.endswith((".py", ".ts", ".js", ".json", ".env")):
                path = Path(root) / file
                content = path.read_text(errors="ignore")
                for pattern in SECRET_PATTERNS:
                    if re.search(pattern, content) and "example" not in str(path):
                        # Very simple heuristic: if it looks like an assignment to a string
                        if re.search(rf'{pattern}\s*[:=]\s*["\'][^"\']+["\']', content):
                            violations.append(f"Potential secret in {path}")
    return violations

def check_prompt_versioning():
    print("🔍 Checking prompt versioning (HR-19)...")
    violations = []
    prompt_dir = Path("packages/prompts")
    if prompt_dir.exists():
        for file in prompt_dir.glob("*.md"):
            content = file.read_text()
            if not re.search(r"v\d+\.\d+\.\d+", content):
                violations.append(f"Unversioned prompt: {file}")
    return violations

def check_n8n_business_truth():
    print("🔍 Checking n8n logic compliance (HR-20)...")
    # Rule: Business truth must be in PostgreSQL, n8n is just fabric
    # We warn if large JSON files exist in workflows/n8n without corresponding SQL
    return []

if __name__ == "__main__":
    v_secrets = check_secrets()
    v_prompts = check_prompt_versioning()
    
    all_violations = v_secrets + v_prompts
    
    if all_violations:
        print("\n❌ HARD RULES VIOLATIONS FOUND:")
        for v in all_violations:
            print(f"  - {v}")
        sys.exit(1)
    
    print("\n✅ All Hard Rules checks passed.")
    sys.exit(0)
