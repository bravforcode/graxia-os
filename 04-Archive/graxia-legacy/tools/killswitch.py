import requests
import sys
import argparse

# Configuration
RC_API_URL = "http://localhost:8001" # Default release-control port

def trigger_killswitch(enabled: bool):
    """
    Triggers the system-wide emergency kill switch.
    """
    flag_key = "block_sensitive_prompt_expansion" # In prod, this would be system.stop_all
    
    print(f"[*] Connecting to BravOS Release Control at {RC_API_URL}...")
    
    try:
        response = requests.patch(
            f"{RC_API_URL}/v1/flags/{flag_key}/toggle",
            params={"enabled": enabled}
        )
        
        if response.status_code == 200:
            status = "ACTIVE" if enabled else "DEACTIVATED"
            print(f"[+] SUCCESS: Emergency Kill Switch is now {status}")
        else:
            print(f"[-] ERROR: Failed to toggle kill switch. Status: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("[-] ERROR: Could not connect to Release Control API. Ensure the service is running.")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BravOS CEO Emergency Kill Switch")
    parser.add_argument("--on", action="store_true", help="Activate Kill Switch (STOP ALL)")
    parser.add_argument("--off", action="store_true", help="Deactivate Kill Switch (RESUME)")
    
    args = parser.parse_args()
    
    if args.on:
        trigger_killswitch(True)
    elif args.off:
        trigger_killswitch(False)
    else:
        parser.print_help()
