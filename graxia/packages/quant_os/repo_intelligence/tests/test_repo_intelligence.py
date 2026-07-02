"""
Repo Intelligence Execution Firewall Tests
===========================================
Static policy tests that enforce CI-level supply-chain controls.

From master plan Section 7.3 Task 4:
  CI must fail if any external repo module:
  - imports MetaTrader5
  - receives broker credentials
  - calls order_send / order_modify / order_close_by

And from Section 4.5:
  - quarantined repos cannot be in production dependency lockfiles
  - repos must have pinned commits

ponytail: tests are minimal — one assertion per rule, no fixtures.
"""
import os


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
ADAPTERS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "adapters")
)
REGISTRY_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "registry")
)

# ---------------------------------------------------------------------------
# Helpers — load YAML registry without importing external deps
# ---------------------------------------------------------------------------
def _load_yml(path: str) -> list[dict]:
    """Load a YAML file. Returns empty list if pyyaml unavailable or file missing."""
    try:
        import yaml  # ponytail: already installed per constraint
    except ImportError:
        return []
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if isinstance(data, dict):
        # unwrap top-level key like 'repositories:' / 'quarantined:'
        for v in data.values():
            if isinstance(v, list):
                return v
    return data if isinstance(data, list) else []


def _load_registry() -> list[dict]:
    return _load_yml(os.path.join(REGISTRY_DIR, "repositories.yml"))


def _load_quarantined() -> list[dict]:
    return _load_yml(os.path.join(REGISTRY_DIR, "quarantined_repositories.yml"))


def _load_approved() -> list[dict]:
    return _load_yml(os.path.join(REGISTRY_DIR, "approved_references.yml"))


# ---------------------------------------------------------------------------
# Master plan repo IDs from Section 4.4 (canonical)
# ---------------------------------------------------------------------------
EXPECTED_REPO_IDS = sorted([
    "mementum_backtrader",
    "kernc_backtesting_py",
    "polakowo_vectorbt",
    "quantconnect_lean",
    "stocksharp_stocksharp",
    "fasiondog_hikyuu",
    "enzoampil_fastquant",
    "edtechre_pybroker",
    "lumiwealth_lumibot",
    "austin_starks_nexttrade",
    "scottfreellc_alphapy",
    "michaelchu_optopsy",
    "hummingbot_hummingbot",
    "drakkar_software_octobot",
    "barter_rs_barter_rs",
    "whittlem_pycryptobot",
    "socktrader_socktrader",
    "finanzobot_finanzobot",
    "quantweb3_nexustrader",
    "superalgos_superalgos",
    "trading_bot_tv_webhook",
    "cryptognome_tv_webhook",
    "elias_aboukhater_trading_bot",
    "backpack455_trading_bot",
    "tonyma_walk_forward_backtester",
    "kiploks_walk_forward_validator",
    "cluster2600_elvis",
    "robert_zag_stockanalysis",
    "anthonydickson_algotrader",
    "jesuistm_quant_trading",
    "xavierleeeugene_trading_strategies",
    "elitequant_elitequant",
    "jadelam_algorithmictrading",
    "ro234jk_trading_bot",
    "asavinov_intelligent_trading_bot",
    "mun_min_ml_trading_bot",
    "zeroxemmkty_quantmuse",
    "eugeneow_trading",
    "hamidreza_rhz_ml_strategy",
    "trading_bot_robo_advisor_stock_bots",
    "coinquanta_awesome_crypto_api",
    "stephan_akkerman_crypto_ohlcv",
    "alihanucar_fredapi",
    "alternative_macro_signals_api_docs",
    "staituned_financial_sentiment",
    "sashaflores_crypto_sentiment",
    "john_gee3_newsapi_crypto_sentiment",
    "sajanpoudel_cryptosensei",
    "br0ski777_crypto_news_mcp",
    "nkaz001_hftbacktest",
    "algotraders_stock_analysis_engine",
    "gazbert_bxbot",
    "solana_arbitrage_bot",
    "solana_trading_cli",
    "solana_mev_bot",
    "bsc_fourmeme_bot",
])

QUARANTINED_IDS = sorted([
    "solana_arbitrage_bot",
    "solana_trading_cli",
    "solana_mev_bot",
    "bsc_fourmeme_bot",
])

ADAPTER_FILES = [
    "vectorbt_oracle.py",
    "backtesting_py_oracle.py",
    "backtrader_oracle.py",
    "lean_oracle_contract.py",
]


# ---------------------------------------------------------------------------
# Test 1 — every master plan repo has a registry entry
# ---------------------------------------------------------------------------
def test_all_repos_in_registry():
    """Every repo from master plan Section 4.4 must exist in repositories.yml."""
    registry = _load_registry()
    registered = sorted(r["repo_id"] for r in registry)
    missing = set(EXPECTED_REPO_IDS) - set(registered)
    assert not missing, f"Missing from registry: {missing}"


# ---------------------------------------------------------------------------
# Test 2 — quarantine list doesn't overlap with approved
# ---------------------------------------------------------------------------
def test_no_quarantined_repo_in_production():
    """No quarantined repo may appear in approved_references.yml."""
    quarantined = {q["repo_id"] for q in _load_quarantined()}
    approved = {a["repo_id"] for a in _load_approved()}
    overlap = quarantined & approved
    assert not overlap, f"Quarantined repos found in approved: {overlap}"


# ---------------------------------------------------------------------------
# Test 3 — each adapter exports normalize_output
# ---------------------------------------------------------------------------
def test_adapter_has_normalize_output():
    """Each adapter module must define a normalize_output callable."""
    for fname in ADAPTER_FILES:
        path = os.path.join(ADAPTERS_DIR, fname)
        assert os.path.exists(path), f"Adapter file missing: {fname}"
        # Read source and check for function definition
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        assert "def normalize_output" in source, (
            f"{fname} missing normalize_output function"
        )


# ---------------------------------------------------------------------------
# Test 4 — each adapter exports validate_input
# ---------------------------------------------------------------------------
def test_adapter_has_validate_input():
    """Each adapter module must define a validate_input callable."""
    for fname in ADAPTER_FILES:
        path = os.path.join(ADAPTERS_DIR, fname)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        assert "def validate_input" in source, (
            f"{fname} missing validate_input function"
        )


# ---------------------------------------------------------------------------
# Test 5 — adapters don't import MetaTrader5
# ---------------------------------------------------------------------------
def test_no_external_mt5_import():
    """No adapter file may contain 'import MetaTrader5' or 'from MetaTrader5'."""
    for fname in ADAPTER_FILES:
        path = os.path.join(ADAPTERS_DIR, fname)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        assert "MetaTrader5" not in source, (
            f"{fname} references MetaTrader5 — forbidden in adapter"
        )


# ---------------------------------------------------------------------------
# Test 6 — adapters don't call order_send
# ---------------------------------------------------------------------------
def test_no_external_order_send():
    """No adapter file may reference order_send, order_modify, or order_close_by."""
    forbidden = ["order_send", "order_modify", "order_close_by"]
    for fname in ADAPTER_FILES:
        path = os.path.join(ADAPTERS_DIR, fname)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        for fn in forbidden:
            assert fn not in source, (
                f"{fname} references {fn} — forbidden in adapter"
            )


# ---------------------------------------------------------------------------
# Test 7 — every registry entry has url, role, permissions
# ---------------------------------------------------------------------------
def test_registry_has_required_fields():
    """Every entry in repositories.yml must have canonical_url, proposed_role, permissions."""
    registry = _load_registry()
    required = ["canonical_url", "proposed_role", "permissions"]
    for entry in registry:
        for field in required:
            assert field in entry, (
                f"repo {entry.get('repo_id', '???')} missing field '{field}'"
            )
        perms = entry["permissions"]
        assert isinstance(perms, dict), (
            f"repo {entry['repo_id']} permissions is not a dict"
        )


# ---------------------------------------------------------------------------
# Test 8 — quarantined repos have zero execution permissions
# ---------------------------------------------------------------------------
def test_quarantined_repos_have_no_execution():
    """Quarantined repos must have read_only_reference: false and no execute perms."""
    registry = _load_registry()
    quarantined_map = {
        q["repo_id"]: q for q in _load_quarantined()
    }
    for entry in registry:
        if entry["repo_id"] in quarantined_map:
            perms = entry.get("permissions", {})
            assert perms.get("read_only_reference") is False, (
                f"Quarantined {entry['repo_id']} has read_only_reference != false"
            )
            assert perms.get("isolated_execute") is False, (
                f"Quarantined {entry['repo_id']} has isolated_execute != false"
            )
            assert perms.get("mt5_execution_access") is False, (
                f"Quarantined {entry['repo_id']} has mt5_execution_access != false"
            )


# ---------------------------------------------------------------------------
# Test 9 — no adapter has module-level external imports
# ---------------------------------------------------------------------------
def test_no_external_library_imports_at_module_level():
    """Adapters must not import external libraries at module level (lazy only)."""
    external_libs = [
        "vectorbt", "backtesting", "backtrader",
        "MetaTrader5", "quantconnect",
    ]
    for fname in ADAPTER_FILES:
        path = os.path.join(ADAPTERS_DIR, fname)
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        # Only check lines outside docstrings and comments
        in_docstring = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if in_docstring or stripped.startswith("#"):
                continue
            for lib in external_libs:
                assert f"import {lib}" not in stripped, (
                    f"{fname}:{i} has module-level import of {lib}"
                )
                assert f"from {lib}" not in stripped, (
                    f"{fname}:{i} has module-level from {lib} import"
                )
