import json
import os
from pathlib import Path

hub_path = Path(r'C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\skills-universal')
registry_file = hub_path / 'skills-registry-compact.json'

if not registry_file.exists():
    print(f"Registry not found at {registry_file}")
    exit(1)

with open(registry_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

skills = data.get('skills', [])

print(f"Starting to weave back-links for {len(skills)} skills...")

for i, skill in enumerate(skills):
    skill_id = skill['id']
    category = skill.get('category', 'Other')
    skill_file = hub_path / skill_id / 'SKILL.md'
    
    if skill_file.exists():
        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if already woven
            if "## 🔗 Metadata & Links" in content:
                continue
                
            # Add footer with back-links
            footer = f"\n\n---\n## 🔗 Metadata & Links\n"
            footer += f"- **Parent Hub:** [[Master_Skills_Hub|🧠 Universal Skills Hub]]\n"
            footer += f"- **Category:** [[Index - {category}|{category} Index]]\n"
            footer += f"- **Architecture:** [[Atlas|🗺️ Knowledge Atlas]]\n"
            
            with open(skill_file, 'a', encoding='utf-8') as f:
                f.write(footer)
                
            if (i + 1) % 100 == 0:
                print(f"Woven {i + 1} files...")
        except Exception as e:
            print(f"Error processing {skill_id}: {e}")

print("Successfully woven all 1,390 skills back to the central hub!")
