#!/usr/bin/env python3
"""
Start Skills API Gateway as a service
Runs on port 8000
"""
import sys
import subprocess
from pathlib import Path

def main():
    skills_api = Path(__file__).parent / "skills_api_gateway.py"
    
    print("🚀 Starting Skills API Gateway...")
    print(f"📍 API file: {skills_api}")
    print()
    print("Listen on: http://localhost:8000")
    print("Swagger docs: http://localhost:8000/docs")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        subprocess.run(
            [sys.executable, str(skills_api)],
            check=False
        )
    except KeyboardInterrupt:
        print("\n✅ API Gateway stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()
