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
categories = {}

# Group by category
for skill in skills:
    cat = skill.get('category', 'Other')
    if cat not in categories:
        categories[cat] = []
    categories[cat].append(skill)

# Create Index files for each category
index_links = []
for cat, items in categories.items():
    file_name = f"Index - {cat}.md".replace('/', '-')
    content = f"# Skills Index: {cat}\n\n"
    content += "This index links to all specialized capabilities within this category.\n\n"
    for item in items:
        # Link to the folder/SKILL.md
        content += f"- [[{item['id']}/SKILL.md|{item['name']}]] — {item.get('description', '')}\n"
    
    with open(hub_path / file_name, 'w', encoding='utf-8') as f:
        f.write(content)
    index_links.append(f"- [[brain/skills-universal/{file_name}|Index - {cat}]] ({len(items)} skills)")

# Create a Master Skills Hub file
hub_content = "# 🧠 Universal Skills Hub\n\n"
hub_content += "A centralized command center for all 1,300+ AI capabilities.\n\n"
hub_content += "## 🗺️ Categorized Indices\n" + "\n".join(sorted(index_links))
hub_content += "\n\n---\n*Part of the Graxia OS Intelligence Architecture.*"

with open(hub_path / "Master_Skills_Hub.md", 'w', encoding='utf-8') as f:
    f.write(hub_content)

print(f"Successfully created {len(categories)} category indices and Master_Skills_Hub.md")
