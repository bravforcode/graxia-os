import os
import re

files = [
    'graxia os/frontend/e2e/chaos/agent_lifecycle.spec.ts',
    'graxia os/frontend/e2e/chaos/auth_security.spec.ts',
    'graxia os/frontend/e2e/chaos/data_integrity.spec.ts',
    'graxia os/frontend/e2e/chaos/resilience.spec.ts'
]

for f_path in files:
    if not os.path.exists(f_path):
        continue
    with open(f_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Remove helper
    content = re.sub(r"async function loginIfRequired[\s\S]*?\n\}", "", content)
    content = content.replace("await loginIfRequired(page);", "")
    
    # Simplify beforeEach
    if "/agents" in f_path:
        target = "/agents"
    elif "/leads" in f_path:
        target = "/leads"
    else:
        target = "/"
        
    pattern = r"test\.beforeEach\(async \(\{ page \}\) => \{[\s\S]*?\}\)"
    replacement = f"test.beforeEach(async ({{ page }}) => {{ await page.goto('{target}'); }})"
    content = re.sub(pattern, replacement, content)
    
    with open(f_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Cleaned {f_path}")
