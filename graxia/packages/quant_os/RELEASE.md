# Release Process

## Prerequisites
```bash
pip install bump2version
```

## Creating a Release

```bash
# Create release branch
git checkout -b release/v{version}

# Bump version (patch/minor/major)
bumpversion --config-file graxia/packages/quant_os/.bumpversion.cfg patch

# Update CHANGELOG.md with release date
# Then commit and tag
git add VERSION pyproject.toml CHANGELOG.md
git commit -m "release(quant_os): v{new_version}"
git tag v{new_version}
git push && git push --tags
```

## Version Scheme
- `x.y.z-dev` → development (default, currently 0.2.0-dev)
- `x.y.z` → release
