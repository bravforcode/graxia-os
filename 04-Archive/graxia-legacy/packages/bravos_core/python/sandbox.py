import docker
from typing import Optional, Dict, Any, List
import logging
import uuid
import tempfile
import os

logger = logging.getLogger("bravos_sandbox")

class DockerSandbox:
    """
    Provides an ephemeral, isolated execution environment for untrusted or experimental 
    agent skills using Docker containers. Enforces strict resource limits and network policies.
    """
    
    def __init__(self):
        try:
            self.client = docker.from_env()
            logger.info("Docker Sandbox client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            self.client = None

    def execute_script(
        self, 
        script_code: str, 
        language: str = "python", 
        timeout_seconds: int = 15,
        network_access: bool = False,
        env_vars: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Executes a piece of code inside a fresh, isolated Docker container.
        """
        if not self.client:
            return {"status": "error", "message": "Docker client not available"}

        if language != "python":
            return {"status": "error", "message": "Currently only python is supported"}

        # Define resource limits for safety
        mem_limit = "128m"  # Max RAM
        cpu_quota = 50000   # 50% of CPU

        image = "python:3.11-slim"
        container_name = f"bravos_sandbox_{uuid.uuid4().hex[:8]}"
        
        # We mount the script into the container as a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py", mode="w") as temp_script:
            temp_script.write(script_code)
            temp_path = temp_script.name

        try:
            # Prepare network settings based on capability grant
            network_mode = "bridge" if network_access else "none"

            # Run the container
            container = self.client.containers.run(
                image,
                command=f"python /app/script.py",
                name=container_name,
                volumes={temp_path: {'bind': '/app/script.py', 'mode': 'ro'}},
                environment=env_vars or {},
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                network_mode=network_mode,
                detach=True,
                auto_remove=False # We handle removal to get logs
            )

            # Wait for container to finish or timeout
            result = container.wait(timeout=timeout_seconds)
            exit_code = result.get("StatusCode", -1)
            
            # Capture output
            logs = container.logs().decode("utf-8")
            
            # Clean up
            container.remove(force=True)
            os.remove(temp_path)
            
            return {
                "status": "success" if exit_code == 0 else "error",
                "exit_code": exit_code,
                "output": logs
            }

        except docker.errors.ContainerError as e:
            # Command failed inside container
            os.remove(temp_path)
            return {"status": "error", "message": str(e), "exit_code": e.exit_status}
        except Exception as e:
            # Timeout or other runtime error
            os.remove(temp_path)
            try:
                # Force cleanup if it timed out while running
                c = self.client.containers.get(container_name)
                c.remove(force=True)
            except:
                pass
            return {"status": "error", "message": str(e), "exit_code": -1}

# Global Instance
sandbox_runner = DockerSandbox()
