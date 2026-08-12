import ast, sys, os, pathlib

third_party = set()
dirs_to_scan = ['app', 'tests']
for d in dirs_to_scan:
    for p in pathlib.Path(d).rglob('*.py'):
        try:
            tree = ast.parse(p.read_text(encoding='utf-8', errors='ignore'))
        except:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split('.')[0]
                    third_party.add(top)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split('.')[0]
                third_party.add(top)

stdlib = sys.stdlib_module_names
external = sorted(third_party - stdlib - {'app'})
print('\n'.join(external))
