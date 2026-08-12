"""
fix_scheduled_tasks.py — Fix all Graxia scheduled tasks with correct triggers
"""
import subprocess, os
from datetime import datetime, timedelta

def run_ps(cmd):
    """Run PowerShell command and return output."""
    r = subprocess.run(
        ['powershell', '-Command', cmd],
        capture_output=True, text=True, timeout=30
    )
    return r.stdout.strip(), r.returncode

def main():
    print("=== FIXING ALL GRAXIA SCHEDULED TASKS ===\n")
    
    vault = r"C:\Users\menum\quant\quant bot"
    quant_os = r"C:\Users\menum\graxia os\graxia\packages\quant_os"
    scripts = r"C:\Users\menum\graxia os\graxia\packages\quant_os\scripts"
    
    # Step 1: Remove all old Graxia tasks
    print("1. Removing old tasks...")
    for task_name in ["Graxia-Bridge-Sync", "Graxia-Bridge-Upgrade", 
                      "Graxia-Bridge-Upgrade-Quick", "Graxia-Bridge-Daily",
                      "Graxia-Bridge-Research", "GraxiaBot_RunNow", 
                      "GraxiaBot_v2", "GraxiaBot_v3"]:
        run_ps(f'Unregister-ScheduledTask -TaskName "{task_name}" -Confirm:$false -ErrorAction SilentlyContinue')
    print("   Done\n")
    
    # Step 2: Create tasks with correct triggers
    tasks = [
        {
            "name": "Graxia-Bridge-Sync",
            "desc": "Graxia data + state sync every 15min",
            "mode": "sync",
            "trigger_type": "recurring_15min",
            "timeout_min": 5,
        },
        {
            "name": "Graxia-Bridge-Upgrade",
            "desc": "Graxia full upgrade pipeline every 6h",
            "mode": "upgrade",
            "trigger_type": "recurring_6h",
            "timeout_min": 120,
        },
        {
            "name": "Graxia-Bridge-Upgrade-Quick",
            "desc": "Graxia quick upgrade every 2h",
            "mode": "upgrade-q",
            "trigger_type": "recurring_2h",
            "timeout_min": 30,
        },
        {
            "name": "Graxia-Bridge-Daily",
            "desc": "Graxia full daily run at 03:00",
            "mode": "full",
            "trigger_type": "daily_0300",
            "timeout_min": 60,
        },
        {
            "name": "Graxia-Bridge-Research",
            "desc": "Graxia NotebookLM research at 04:00",
            "mode": "pull-only",
            "trigger_type": "daily_0400",
            "timeout_min": 30,
        },
    ]
    
    for task in tasks:
        print(f"2. Creating {task['name']}...")
        
        # Build PowerShell script for this task
        if task["trigger_type"] == "daily_0300":
            trigger_ps = 'New-ScheduledTaskTrigger -Daily -At "03:00"'
        elif task["trigger_type"] == "daily_0400":
            trigger_ps = 'New-ScheduledTaskTrigger -Daily -At "04:00"'
        else:
            # Recurring tasks: use -Once with future start + repetition
            interval_map = {
                "recurring_15min": (timedelta(minutes=15), timedelta(days=365)),
                "recurring_2h": (timedelta(hours=2), timedelta(days=365)),
                "recurring_6h": (timedelta(hours=6), timedelta(days=365)),
            }
            interval, duration = interval_map[task["trigger_type"]]
            start_time = (datetime.now() + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
            
            # Convert to PowerShell TimeSpan format
            if interval.total_seconds() >= 3600:
                interval_str = f'New-TimeSpan -Hours {int(interval.total_seconds()//3600)}'
            else:
                interval_str = f'New-TimeSpan -Minutes {int(interval.total_seconds()//60)}'
            
            duration_str = f'New-TimeSpan -Days {int(duration.total_seconds()//86400)}'
            
            trigger_ps = f'New-ScheduledTaskTrigger -Once -At "{start_time}" -RepetitionInterval {interval_str} -RepetitionDuration {duration_str}'
        
        # Build the full PowerShell command
        ps_script = f'''
$ErrorActionPreference = "Stop"
$vault = "{vault}"
$quantOs = "{quant_os}"
$scripts = "{scripts}"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File \\"$scripts\\run_bridge.ps1\\" -Mode {task['mode']}" `
    -WorkingDirectory $quantOs

$trigger = {trigger_ps}

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes {task['timeout_min']}) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName "{task['name']}" `
    -Description "{task['desc']}" `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Write-Host "  OK: {task['name']}"
'''
        
        # Write to temp file and execute with elevation
        temp_ps = os.path.join(os.environ['TEMP'], f"fix_task_{task['name']}.ps1")
        with open(temp_ps, 'w') as f:
            f.write(ps_script)
        
        # Run with elevation
        r = subprocess.run(
            ['powershell', '-ExecutionPolicy', 'Bypass', '-File', temp_ps],
            capture_output=True, text=True, timeout=30
        )
        
        if r.returncode == 0:
            print(f"   {r.stdout.strip()}")
        else:
            print(f"   ERROR: {r.stderr[:200]}")
    
    # Step 3: Verify
    print("\n3. Verifying tasks...")
    stdout, _ = run_ps('Get-ScheduledTask -TaskName "Graxia-Bridge*" | Select-Object TaskName, State | Format-Table -AutoSize')
    print(stdout)
    
    # Step 4: Test one task manually
    print("4. Testing Graxia-Bridge-Sync manually...")
    stdout, _ = run_ps('Start-ScheduledTask -TaskName "Graxia-Bridge-Sync"; Start-Sleep 3; $t = Get-ScheduledTask -TaskName "Graxia-Bridge-Sync"; $i = Get-ScheduledTaskInfo -TaskName "Graxia-Bridge-Sync"; Write-Host "State: $($t.State) | LastRun: $($i.LastRunTime) | Result: $($i.LastTaskResult)"')
    print(f"   {stdout}")
    
    print("\n=== DONE ===")

if __name__ == "__main__":
    main()
