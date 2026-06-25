"""Setup shim — build config lives in pyproject.toml."""
from setuptools import setup, find_packages

setup(
    name="quant_os",
    version="0.2.0-dev",
    packages=find_packages(),
    install_requires=["MetaTrader5"],
    python_requires=">=3.11",
)
