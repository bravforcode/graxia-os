@echo off
set PY=C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe
set WD=C:\Users\menum\graxia os\graxia\packages\quant_os
cd /d "%WD%"

echo ==========================================
echo [1/5] reconcile_trial_ledger.py
echo ==========================================
%PY% scripts\reconcile_trial_ledger.py
echo EXIT CODE: %ERRORLEVEL%

echo.
echo ==========================================
echo [2/5] edge_search_cross_sectional (base)
echo ==========================================
%PY% scripts\edge_search_cross_sectional.py --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 --cost-model pepperstone_razor --dk-test pooled --label-shuffle 200 --min-years 8 --output reports\edge_search_cross_sectional_20260720.json
echo EXIT CODE: %ERRORLEVEL%

echo.
echo ==========================================
echo [3/5] edge_search cost stress 1.5x
echo ==========================================
%PY% scripts\edge_search_cross_sectional.py --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 --cost-model pepperstone_razor --cost-multiplier 1.5 --dk-test pooled --output reports\edge_search_cost_stress_1.5x_20260720.json
echo EXIT CODE: %ERRORLEVEL%

echo.
echo ==========================================
echo [4/5] edge_search cost stress 2.0x
echo ==========================================
%PY% scripts\edge_search_cross_sectional.py --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 --cost-model pepperstone_razor --cost-multiplier 2.0 --dk-test pooled --output reports\edge_search_cost_stress_2.0x_20260720.json
echo EXIT CODE: %ERRORLEVEL%

echo.
echo ==========================================
echo [5/5] jackknife_asset_robustness.py
echo ==========================================
%PY% scripts\jackknife_asset_robustness.py --universe XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,NAS100,US30 --trial 2001 --output reports\jackknife_robustness_20260720.json
echo EXIT CODE: %ERRORLEVEL%

echo.
echo ==========================================
echo ALL DONE
echo ==========================================
