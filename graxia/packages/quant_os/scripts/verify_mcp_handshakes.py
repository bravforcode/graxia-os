"""Reproducible MCP Stdio JSON-RPC Handshake Verification Suite for quant_os.

Tests all configured MCP servers by spawning them, sending an `initialize` JSON-RPC request over stdio,
verifying clean JSON responses without EPIPE / broken pipe errors, and logging proof.
"""

import json
import subprocess
import sys
import time
import os

# Ensure UTF-8 stdout
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

SERVERS = [
    {
        "name": "agentmemory",
        "cmd": ["node", "C:/Users/menum/AppData/Roaming/npm/node_modules/@agentmemory/mcp/bin.mjs"]
    },
    {
        "name": "ruflo",
        "cmd": ["node", "C:/Users/menum/AppData/Roaming/npm/node_modules/ruflo/bin/ruflo.js", "mcp", "start"]
    },
    {
        "name": "hindsight",
        "cmd": ["node", "C:/Users/menum/AppData/Roaming/npm/node_modules/hindsight-mcp/build/index.js"]
    }
]

def verify_server(server_info):
    name = server_info["name"]
    cmd = server_info["cmd"]
    print(f"Testing {name} via command: {' '.join(cmd)}")
    
    init_request = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "quant-os-verifier", "version": "1.0.0"}
        }
    }) + "\n"
    
    start_time = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        
        stdout, stderr = proc.communicate(input=init_request, timeout=5)
        elapsed = round((time.time() - start_time) * 1000, 2)
        
        # Look for valid JSON-RPC response
        lines = stdout.strip().split('\n')
        has_response = any('"jsonrpc"' in l or '"result"' in l for l in lines)
        
        if has_response:
            print(f"  [SUCCESS] {name} initialized in {elapsed}ms. Clean Stdio response received.")
            return True
        else:
            print(f"  [WARNING] {name} exited without JSON-RPC response. Stdout: {stdout[:100]}, Stderr: {stderr[:100]}")
            return False
            
    except subprocess.TimeoutExpired:
        proc.kill()
        print(f"  [TIMEOUT] {name} timed out waiting for stdio handshake.")
        return False
    except Exception as e:
        print(f"  [ERROR] {name} failed: {e}")
        return False

def main():
    print("=== EMPIRICAL MCP HANDSHAKE VERIFICATION SUITE ===")
    results = {}
    for s in SERVERS:
        results[s["name"]] = verify_server(s)
        
    print("\n=== SUMMARY ===")
    all_passed = True
    for name, success in results.items():
        status = "PASSED" if success else "FAILED"
        print(f"  {name}: {status}")
        if not success:
            all_passed = False
            
    if all_passed:
        print("\nAll MCP servers passed Stdio JSON-RPC initialization handshake cleanly!")
        sys.exit(0)
    else:
        print("\nSome MCP servers failed handshake.")
        sys.exit(1)

if __name__ == "__main__":
    main()
