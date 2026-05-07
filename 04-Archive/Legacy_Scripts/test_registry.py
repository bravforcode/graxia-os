import json

registry_file = r"C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\brain\ai-gateway\skills-registry.json"

with open(registry_file, encoding='utf-8') as f:
    registry = json.load(f)

print(f"✅ Registry loaded successfully")
print(f"Version: {registry.get('version')}")
print(f"Generated: {registry.get('generated')}")
print(f"Total skills: {len(registry['skills'])}")
print()
print("Skills:")
for skill_id, skill in list(registry['skills'].items())[:10]:
    print(f"  - {skill_id}: {skill['name']}")
    
if len(registry['skills']) > 10:
    print(f"  ... and {len(registry['skills']) - 10} more")
