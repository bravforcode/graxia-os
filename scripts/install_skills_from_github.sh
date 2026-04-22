#!/bin/bash

# Configuration
VAULT_DIR="C:/Users/menum/Documents/ObsidianVault/Second Brain/skills"
BRAIN_DIR="C:/Users/menum/Documents/ObsidianVault/Second Brain/brain"
INDEX_FILE="$BRAIN_DIR/skills-catalog.md"

REPOS=(
  "anthropics/skills"
  "addyosmani/agent-skills"
  "panitw/todo4-onboard-skill"
  "shanraisshan/claude-code-best-practice"
  "JuliusBrussee/caveman"
  "rtk-ai/rtk"
  "kepano/obsidian-skills"
  "skyliner2008/PersonalAIOnMobile"
)

# Ensure directories exist
mkdir -p "$VAULT_DIR"
mkdir -p "$BRAIN_DIR"

# Initialize index
echo "# Skills Catalog" > "$INDEX_FILE"
echo "" >> "$INDEX_FILE"
echo "Auto-generated from GitHub repositories." >> "$INDEX_FILE"
echo "" >> "$INDEX_FILE"

TMP_DIR=$(mktemp -d)
cd "$TMP_DIR" || exit 1

for REPO in "${REPOS[@]}"; do
  echo "Processing $REPO..."
  OWNER=$(echo "$REPO" | cut -d'/' -f1)
  REPO_NAME=$(echo "$REPO" | cut -d'/' -f2)
  
  mkdir -p "$VAULT_DIR/$OWNER"
  
  git clone --depth 1 "https://github.com/$REPO.git" "$REPO_NAME" 2>/dev/null
  
  if [ -d "$REPO_NAME" ]; then
    echo "## $REPO" >> "$INDEX_FILE"
    
    # Find all .md files, exclude README if it's just the repo description
    find "$REPO_NAME" -type f -name "*.md" | while read -r FILE; do
      BASENAME=$(basename "$FILE")
      DEST="$VAULT_DIR/$OWNER/$BASENAME"
      
      # Add YAML frontmatter
      echo "---" > "$DEST"
      echo "source: github" >> "$DEST"
      echo "repo: $REPO" >> "$DEST"
      echo "loaded: false" >> "$DEST"
      echo "auto_load_context: []" >> "$DEST"
      echo "---" >> "$DEST"
      echo "" >> "$DEST"
      
      cat "$FILE" >> "$DEST"
      
      echo "- [[skills/$OWNER/$BASENAME|$BASENAME]]" >> "$INDEX_FILE"
    done
    echo "" >> "$INDEX_FILE"
  else
    echo "Failed to clone $REPO"
  fi
done

cd - >/dev/null || exit 1
rm -rf "$TMP_DIR"

echo "Skills installation complete! Check $INDEX_FILE"
