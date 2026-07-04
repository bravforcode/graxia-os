"""
Setup Windows Task Scheduler for TSM Paper Trading
Run this script as Administrator to schedule the bot.
"""
import subprocess
import sys
from pathlib import Path


def setup_schedule():
    """Create a Windows Task Scheduler task for paper trading."""
    
    bat_path = Path(__file__).parent / "run_paper_trading.bat"
    
    # Create the batch file if it doesn't exist
    if not bat_path.exists():
        bat_path.write_text(f"""@echo off
cd /d "C:\\Users\\menum\\graxia os\\graxia\\packages\\quant_os"
python scripts/tsm_paper_trade.py --live
""")
    
    # PowerShell command to create the task
    ps_cmd = f"""
    $action = New-ScheduledTaskAction -Execute '{bat_path}'
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '01:30'
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
    Register-ScheduledTask -TaskName 'TSM_Paper_Trading' -Action $action -Trigger $trigger -Settings $settings -Force
    """
    
    print("Creating scheduled task...")
    print(f"  Task: TSM_Paper_Trading")
    print(f"  Schedule: Mon-Fri at 01:30 UTC")
    print(f"  Script: {bat_path}")
    
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            check=True
        )
        print("✅ Task created successfully!")
        
        # Verify
        verify_cmd = "Get-ScheduledTask -TaskName 'TSM_Paper_Trading' | Select-Object TaskName, State"
        verify = subprocess.run(
            ["powershell", "-Command", verify_cmd],
            capture_output=True,
            text=True
        )
        print(verify.stdout)
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create task: {e.stderr}")
        print("\nRun this script as Administrator:")
        print("  Right-click → Run as administrator")


if __name__ == "__main__":
    setup_schedule()
