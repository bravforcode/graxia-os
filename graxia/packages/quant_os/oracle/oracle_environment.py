"""Phase BE-P5 — Oracle environment isolation."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OracleEnvironment:
    name: str
    python_version: str
    framework_version: str
    adapter_version: str
    license_decision: str
    sbom_entry: str = ""
    has_broker_credentials: bool = False
    has_mt5_execution: bool = False
    has_shared_writable: bool = False
    
    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if self.has_broker_credentials:
            issues.append("must not have broker credentials")
        if self.has_mt5_execution:
            issues.append("must not have MT5 execution permission")
        if self.has_shared_writable:
            issues.append("must not have shared writable artifact directory")
        if not self.python_version:
            issues.append("python_version required")
        if not self.framework_version:
            issues.append("framework_version required")
        return len(issues) == 0, issues


class OracleEnvironmentManager:
    """Manages isolated oracle environments."""
    
    def __init__(self, envs_dir: str = ""):
        self._envs_dir = Path(envs_dir) if envs_dir else Path(".envs")
        self._environments: dict[str, OracleEnvironment] = {}
    
    def register(self, env: OracleEnvironment) -> None:
        self._environments[env.name] = env
    
    def get(self, name: str) -> OracleEnvironment | None:
        return self._environments.get(name)
    
    def list_all(self) -> list[str]:
        return list(self._environments.keys())
    
    def validate_all(self) -> dict[str, tuple[bool, list[str]]]:
        results = {}
        for name, env in self._environments.items():
            results[name] = env.validate()
        return results
    
    def ensure_dirs(self) -> list[str]:
        """Create environment directories."""
        created = []
        for name in self._environments:
            env_dir = self._envs_dir / name
            env_dir.mkdir(parents=True, exist_ok=True)
            created.append(str(env_dir))
        return created
