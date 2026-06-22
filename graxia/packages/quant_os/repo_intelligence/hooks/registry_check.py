#!/usr/bin/env python3
"""Check that registry YAML is valid and entries have required fields."""
import sys
import os
import yaml

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), '..', 'registry', 'repositories_canonical.yml')

def run_check():
    if not os.path.exists(REGISTRY_PATH):
        print("WARN: registry not found")
        return 0
    
    with open(REGISTRY_PATH) as f:
        data = yaml.safe_load(f)
    
    if not isinstance(data, list):
        print("ERROR: registry must be a list")
        return 1
    
    required_fields = ['name', 'tier', 'role', 'asset_class']
    issues = []
    for entry in data:
        for field in required_fields:
            if field not in entry:
                issues.append(f"Entry {entry.get('name', 'UNKNOWN')}: missing {field}")
    
    if issues:
        print("REGISTRY ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    
    print(f"Registry check: OK ({len(data)} entries)")
    return 0

if __name__ == "__main__":
    sys.exit(run_check())
