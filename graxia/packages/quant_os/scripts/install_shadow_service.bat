@echo off
nssm install QuantOS-Shadow "%PYTHON%" "%~dp0..\run_shadow.py"
nssm set QuantOS-Shadow AppDirectory "%~dp0.."
nssm set QuantOS-DisplayName "QuantOS Shadow Runner"
nssm set QuantOS-Description "Shadow mode tick collection and signal monitoring"
nssm set QuantOS-Start SERVICE_AUTO_START
nssm set QuantOS-AppRestartDelay 10000
nssm set QuantOS-StdoutCreationDisposition 4
nssm set QuantOS-StderrCreationDisposition 4
nssm set QuantOS-AppStdout "%~dp0..\logs\shadow_stdout.log"
nssm set QuantOS-AppStderr "%~dp0..\logs\shadow_stderr.log"
echo QuantOS Shadow service installed.
