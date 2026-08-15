@echo off
rem Wrapper for the Trial 4002 funding-arb paper-trade collector.
rem Invoked by the Windows Scheduled Task "quant_os_funding_arb"
rem (see schedule_funding_arb.ps1). Runs from the package root so the
rem script's ROOT/STATE_PATH resolution is stable, and appends output to
rem reports/paper_trading/funding_arb_run.log.
cd /d "%~dp0.."
python scripts\paper_trade_funding_arb.py >> reports\paper_trading\funding_arb_run.log 2>&1
