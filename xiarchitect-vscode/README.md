# xiarchitect VS Code Extension

This package is the IDE shell for the local `xiarchitect` Python engine that lives in the same repository.

Current scope:

- register the core `xiarchitect:*` commands
- run the Python engine against the active workspace
- load `docs/xiarchitect/*.json` artifacts back into VS Code
- expose a sidebar tree and explorer webview

The extension is intentionally thin. Static analysis, graph generation, and diagram generation stay in the Python engine so the IDE layer can remain a focused adapter.
