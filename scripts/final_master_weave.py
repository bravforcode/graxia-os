import os
from pathlib import Path
import re

hub_path = Path(r'C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\skills-universal')
atlas_path = "[[Atlas|🗺️ Knowledge Atlas]]"
master_hub_path = "[[Master_Skills_Hub|🧠 Universal Skills Hub]]"

print("Starting Final Master Weave...")

if not hub_path.exists():
    print(f"Hub path not found: {hub_path}")
    exit(1)

# 1. Identify all actual markdown files in the hub
all_md_files = list(hub_path.glob('**/*.md'))
# Exclude hub and index files themselves
skill_files = [f for f in all_md_files if f.name != 'Master_Skills_Hub.md' and not f.name.startswith('Index -')]

print(f"Found {len(skill_files)} skill files to process.")

category_map = {}

# 2. Process each skill file to add back-links and identify its category
for i, file_path in enumerate(skill_files):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Determine category from frontmatter or parent folder
        category = "Other"
        fm_match = re.search(r'category:\s*(.*)', content)
        if fm_match:
            category = fm_match.group(1).strip().strip('"\'')
        elif file_path.parent != hub_path:
            category = file_path.parent.name
            
        if category not in category_map:
            category_map[category] = []
        
        # Store relative link for index (Obsidian style)
        # For files in root, it's just [[filename]]
        # For files in subfolder, it's [[subfolder/filename]]
        if file_path.parent == hub_path:
            rel_link = file_path.name
        else:
            rel_link = f"{file_path.parent.name}/{file_path.name}"
            
        display_name = file_path.stem if file_path.name != 'SKILL.md' else file_path.parent.name
        category_map[category].append(f"- [[{rel_link}|{display_name}]]")

        # Add Back-links Footer if not present
        if "## 🔗 Metadata & Links" not in content:
            footer = f"\n\n---\n## 🔗 Metadata & Links\n"
            footer += f"- **Parent Hub:** {master_hub_path}\n"
            footer += f"- **Category:** [[Index - {category}|{category} Index]]\n"
            footer += f"- **Architecture:** {atlas_path}\n"
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(footer)
                
        if (i + 1) % 100 == 0:
            print(f"Processed {i + 1} files...")
                
    except Exception as e:
        print(f"Error processing {file_path}: {e}")

# 3. Re-generate Category Indices with CORRECT links
for cat, links in category_map.items():
    # Clean category name for filename - be very aggressive for Windows
    safe_cat = re.sub(r'[^a-zA-Z0-9_\-]', '_', cat)
    index_file = hub_path / f"Index - {safe_cat}.md"
    content = f"# Skills Index: {cat}\n\n"
    content += "## 🔗 Back to Hub\n"
    content += f"- {master_hub_path}\n"
    content += f"- {atlas_path}\n\n"
    content += "## 🛠️ Capabilities\n"
    content += "\n".join(sorted(links))
    
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(content)

# 4. Re-generate Master Hub
index_list = []
for cat, links in category_map.items():
    safe_cat = re.sub(r'[^a-zA-Z0-9_\-]', '_', cat)
    index_list.append(f"- [[Index - {safe_cat}|{cat} Index]] ({len(links)} skills)")
hub_content = f"# 🧠 Universal Skills Hub\n\n## 🔗 Navigation\n- {atlas_path}\n\n## 🗺️ Categorized Indices\n" 
hub_content += "\n".join(sorted(index_list))
hub_content += "\n\n---\n*Woven by Graxia OS Master Orchestrator.*"

with open(hub_path / "Master_Skills_Hub.md", 'w', encoding='utf-8') as f:
    f.write(hub_content)

print(f"Master Weave Complete. Processed {len(skill_files)} files across {len(category_map)} categories.")
