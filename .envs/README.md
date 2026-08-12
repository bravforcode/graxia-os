# Oracle Environments

Each oracle runs in an isolated virtual environment.
Canonical runtime MUST NOT import from these environments.

## Structure
- canonical/: Main quant_os runtime
- oracle-vectorbt/: VectorBT research oracle
- oracle-backtesting-py/: Backtesting.py research oracle
- oracle-backtrader/: Backtrader research oracle

## Rules
1. Each environment has its own lockfile
2. Oracle packages are NOT installed in canonical
3. Canonical runtime has no import path to oracle packages
4. Every oracle run produces normalized ledgers
5. Differential comparison happens outside all environments
