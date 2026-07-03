"""Setup shim — build config lives in pyproject.toml."""
from setuptools import setup, find_packages

setup(
    name="quant_os",
    version="0.2.0-dev",
    package_dir={"quant_os": "."},
    packages=["quant_os"] + [f"quant_os.{p}" for p in find_packages(where=".")],
    install_requires=["MetaTrader5"],
    python_requires=">=3.11",
)
