"""Smoke tests for monitoring infrastructure — Prometheus metrics, Alertmanager, alert rules."""

import socket
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

BASE = Path(__file__).resolve().parent.parent
MONITORING = BASE / "monitoring"


# ---------------------------------------------------------------------------
# 1. Metrics exporter — server starts, metrics are registered
# ---------------------------------------------------------------------------
class TestMetricsExporter:
    def test_start_metrics_server_binds_port(self):
        """Verify start_metrics_server opens a TCP socket."""
        from quant_os.monitoring.metrics_exporter import start_metrics_server

        # Use a high port to avoid conflicts
        test_port = 19090
        with patch("quant_os.monitoring.metrics_exporter._metrics_started", False):
            start_metrics_server(port=test_port)
            # Give it a moment
            import time

            time.sleep(0.3)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                result = sock.connect_ex(("127.0.0.1", test_port))
                assert result == 0, f"Port {test_port} not open after start_metrics_server"
            finally:
                sock.close()

    def test_all_expected_metrics_exist(self):
        """All metrics referenced in alert rules must be registered."""
        from prometheus_client import REGISTRY

        metric_names = {m for m in REGISTRY._names_to_collectors}
        expected = [
            "quant_os_drawdown_pct",
            "quant_os_kill_switch_active",
            "quant_os_heartbeat_timestamp",
            "quant_os_model_staleness_seconds",
            "quant_os_trades_total",
            "quant_os_daily_pnl",
            "quant_os_open_positions",
            "quant_os_win_rate",
            "quant_os_execution_latency_seconds",
            "quant_os_tsm_last_data_timestamp",
            "quant_os_tsm_last_rebalance_timestamp",
        ]
        for name in expected:
            assert name in metric_names, f"Metric '{name}' not registered in prometheus_client"

    def test_record_trade_increments_counter(self):
        """record_trade should increment the counter and set PnL."""
        from quant_os.monitoring.metrics_exporter import DAILY_PNL, TRADES_TOTAL, record_trade

        before = TRADES_TOTAL.labels(symbol="XAUUSD", side="BUY")._value.get()
        record_trade(symbol="XAUUSD", side="BUY", pnl=123.45)
        after = TRADES_TOTAL.labels(symbol="XAUUSD", side="BUY")._value.get()
        assert after > before
        assert DAILY_PNL._value.get() == 123.45

    def test_update_kill_switch_sets_gauge(self):
        """update_kill_switch sets gauge to 1 when active."""
        from quant_os.monitoring.metrics_exporter import KILL_SWITCH, update_kill_switch

        update_kill_switch(True)
        assert KILL_SWITCH._value.get() == 1.0
        update_kill_switch(False)
        assert KILL_SWITCH._value.get() == 0.0


# ---------------------------------------------------------------------------
# 2. Alert rules — YAML validity and metric name alignment
# ---------------------------------------------------------------------------
class TestAlertRules:
    @pytest.fixture
    def alert_rules(self):
        alert_file = MONITORING / "tsm_alerts.yml"
        with open(alert_file, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_alert_rules_yaml_valid(self, alert_rules):
        """Alert rules file must parse as valid YAML with groups."""
        assert "groups" in alert_rules
        assert len(alert_rules["groups"]) > 0

    def test_all_rules_have_required_fields(self, alert_rules):
        """Every rule must have alert, expr, for, labels, annotations."""
        for group in alert_rules["groups"]:
            for rule in group.get("rules", []):
                assert "alert" in rule, "Rule missing 'alert' field"
                assert "expr" in rule, f"Rule {rule.get('alert')} missing 'expr'"
                assert "for" in rule, f"Rule {rule.get('alert')} missing 'for'"
                assert "labels" in rule, f"Rule {rule.get('alert')} missing 'labels'"
                assert "annotations" in rule, f"Rule {rule.get('alert')} missing 'annotations'"
                assert "severity" in rule["labels"], f"Rule {rule.get('alert')} missing severity label"

    def test_critical_rules_use_correct_metric_names(self, alert_rules):
        """Critical alert expressions must reference metrics that exist in metrics_exporter."""
        from prometheus_client import REGISTRY

        registered = set(REGISTRY._names_to_collectors)

        critical_group = next(g for g in alert_rules["groups"] if g["name"] == "tsm_portfolio_critical")
        for rule in critical_group["rules"]:
            expr = rule["expr"]
            # Extract metric name from expr (first word before { or space)
            metric = expr.split("{")[0].split("(")[0].strip()
            # Some metrics use function wrappers like time() - metric
            # For simple comparisons, the metric is the LHS
            if metric == "time":
                # expr is like: time() - metric > threshold
                parts = expr.split("-")
                if len(parts) > 1:
                    metric = parts[1].strip().split("{")[0].split()[0]
            assert metric in registered, (
                f"Rule '{rule['alert']}' references metric '{metric}' " f"which is not registered in metrics_exporter"
            )

    def test_data_health_rules_use_correct_metric_names(self, alert_rules):
        """Data health rules reference metrics from metrics_exporter."""
        from prometheus_client import REGISTRY

        registered = set(REGISTRY._names_to_collectors)

        data_group = next(g for g in alert_rules["groups"] if g["name"] == "tsm_data_health")
        for rule in data_group["rules"]:
            expr = rule["expr"]
            # Extract metric names from expressions like (time() - metric) > N
            # or metric > N
            for part in expr.replace("(", "").replace(")", "").split():
                # Skip pure numbers, operators, comparisons
                if part.replace(".", "").replace("-", "").isdigit():
                    continue
                if part in ("time", ">", "<", "==", "and", "or", "!="):
                    continue
                # Could be a metric name
                candidate = part.split("{")[0]
                if candidate.startswith("quant_os_"):
                    assert candidate in registered, (
                        f"Rule '{rule['alert']}' references metric '{candidate}' "
                        f"which is not registered in metrics_exporter"
                    )

    def test_all_rules_have_severity_labels(self, alert_rules):
        """Every rule must have severity = critical or warning."""
        for group in alert_rules["groups"]:
            for rule in group.get("rules", []):
                severity = rule["labels"].get("severity")
                assert severity in ("critical", "warning"), f"Rule {rule['alert']} has invalid severity: {severity}"

    def test_drawdown_threshold_matches_code(self, alert_rules):
        """Drawdown alert threshold (15%) must match AUTO_STOP_THRESHOLD_PCT in paper bot."""
        critical_group = next(g for g in alert_rules["groups"] if g["name"] == "tsm_portfolio_critical")
        drawdown_rule = next(r for r in critical_group["rules"] if r["alert"] == "PortfolioDrawdownBreach")
        # Extract threshold from expr: quant_os_drawdown_pct{portfolio="tsm"} > 15
        threshold = float(drawdown_rule["expr"].split(">")[-1].strip())
        # tsm_paper_trade.py has AUTO_STOP_THRESHOLD_PCT = 15.0
        assert threshold == 15.0, f"Drawdown threshold {threshold} != expected 15.0"


# ---------------------------------------------------------------------------
# 3. Prometheus config — scrape targets and alertmanager wiring
# ---------------------------------------------------------------------------
class TestPrometheusConfig:
    @pytest.fixture
    def prom_config(self):
        prom_file = MONITORING / "prometheus.yml"
        with open(prom_file, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_prometheus_config_valid_yaml(self, prom_config):
        """prometheus.yml must parse as valid YAML."""
        assert "global" in prom_config
        assert "scrape_configs" in prom_config

    def test_alertmanager_wiring(self, prom_config):
        """Prometheus must have alerting config pointing to alertmanager."""
        assert "alerting" in prom_config, "No alerting block in prometheus.yml"
        am_configs = prom_config["alerting"].get("alertmanagers", [])
        assert len(am_configs) > 0, "No alertmanager targets configured"
        targets = am_configs[0].get("static_configs", [{}])[0].get("targets", [])
        assert any("alertmanager" in t for t in targets), f"Alertmanager target not found: {targets}"

    def test_rule_files_configured(self, prom_config):
        """Prometheus must reference tsm_alerts.yml."""
        rule_files = prom_config.get("rule_files", [])
        assert any("tsm_alerts.yml" in f for f in rule_files), f"tsm_alerts.yml not in rule_files: {rule_files}"

    def test_paper_bot_scrape_target(self, prom_config):
        """Prometheus must scrape the paper bot metrics endpoint."""
        jobs = prom_config["scrape_configs"]
        paper_job = next((j for j in jobs if j["job_name"] == "tsm-paper-bot"), None)
        assert paper_job is not None, "No 'tsm-paper-bot' scrape job"
        targets = paper_job["static_configs"][0]["targets"]
        assert any("9090" in t for t in targets), f"Paper bot target must include port 9090: {targets}"

    def test_paper_job_has_portfolio_label(self, prom_config):
        """Paper bot scrape job must include portfolio=tsm label for alert matching."""
        jobs = prom_config["scrape_configs"]
        paper_job = next(j for j in jobs if j["job_name"] == "tsm-paper-bot")
        labels = paper_job["static_configs"][0].get("labels", {})
        assert labels.get("portfolio") == "tsm", f"Paper bot missing portfolio=tsm label: {labels}"


# ---------------------------------------------------------------------------
# 4. Alertmanager config — valid YAML, Telegram receiver
# ---------------------------------------------------------------------------
class TestAlertmanagerConfig:
    @pytest.fixture
    def am_config(self):
        am_file = MONITORING / "alertmanager.yml"
        with open(am_file, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_alertmanager_config_valid_yaml(self, am_config):
        """alertmanager.yml must parse as valid YAML."""
        assert "route" in am_config
        assert "receivers" in am_config

    def test_has_telegram_receiver(self, am_config):
        """Must have a receiver configured for Telegram."""
        receivers = am_config["receivers"]
        telegram_found = False
        for r in receivers:
            if "telegram_configs" in r:
                telegram_found = True
                break
        assert telegram_found, "No Telegram receiver in alertmanager.yml"

    def test_route_tree_structure(self, am_config):
        """Route must have receiver, group_by, and child routes."""
        route = am_config["route"]
        assert "receiver" in route
        assert "group_by" in route
        assert "routes" in route
        # Must have at least 2 child routes (critical + warning)
        assert len(route["routes"]) >= 2

    def test_critical_route_uses_different_receiver(self, am_config):
        """Critical alerts should route to a dedicated receiver."""
        route = am_config["route"]
        critical_route = next(
            (r for r in route["routes"] if r.get("match", {}).get("severity") == "critical"),
            None,
        )
        assert critical_route is not None, "No critical severity route"
        # Critical receiver should be different from the default catch-all
        assert (
            critical_route["receiver"] != route["receiver"]
        ), "Critical route uses same receiver as default — should be dedicated"

    def test_inhibit_rules_exist(self, am_config):
        """Inhibit rules should silence warnings when critical is firing."""
        assert "inhibit_rules" in am_config
        rules = am_config["inhibit_rules"]
        assert len(rules) > 0
        # Should match critical → inhibit warning
        assert rules[0]["source_match"]["severity"] == "critical"
        assert rules[0]["target_match"]["severity"] == "warning"


# ---------------------------------------------------------------------------
# 5. Docker-compose — Alertmanager service and Prometheus alertmanager wiring
# ---------------------------------------------------------------------------
class TestDockerCompose:
    @pytest.fixture
    def compose(self):
        compose_file = BASE / "docker-compose.yml"
        with open(compose_file, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_alertmanager_service_exists(self, compose):
        """docker-compose must define an alertmanager service."""
        services = compose.get("services", {})
        assert "alertmanager" in services, "No alertmanager service in docker-compose.yml"

    def test_alertmanager_service_config(self, compose):
        """Alertmanager service must have correct image, port, and volume."""
        am = compose["services"]["alertmanager"]
        assert "alertmanager" in am["image"], f"Wrong image: {am['image']}"
        # Port 9093
        ports = am.get("ports", [])
        assert any("9093" in str(p) for p in ports), f"Missing port 9093: {ports}"
        # Volume mount for config
        volumes = am.get("volumes", [])
        assert any("alertmanager.yml" in str(v) for v in volumes), f"Missing alertmanager.yml volume mount: {volumes}"

    def test_alertmanager_has_network(self, compose):
        """Alertmanager must be on the graxia-trading-net network."""
        am = compose["services"]["alertmanager"]
        networks = am.get("networks", {})
        assert "graxia-trading-net" in networks, "Alertmanager not on trading network"

    def test_alertmanager_volume_declared(self, compose):
        """alertmanager_data volume must be declared."""
        volumes = compose.get("volumes", {})
        assert "alertmanager_data" in volumes, "alertmanager_data volume not declared"

    def test_prometheus_alertmanager_wiring(self, compose):
        """Prometheus service must have alertmanager in its config or be wired via alerting."""
        prom = compose["services"]["prometheus"]
        # Prometheus should mount tsm_alerts.yml
        volumes = prom.get("volumes", [])
        assert any("tsm_alerts.yml" in str(v) for v in volumes), f"Prometheus missing tsm_alerts.yml volume: {volumes}"

    def test_prometheus_extra_hosts_for_docker_internal(self, compose):
        """Prometheus must have host.docker.internal for scraping host services."""
        prom = compose["services"]["prometheus"]
        extra = prom.get("extra_hosts", [])
        assert any(
            "host.docker.internal" in str(h) for h in extra
        ), "Prometheus missing host.docker.internal extra_host"


# ---------------------------------------------------------------------------
# 6. Paper bot — imports metrics_exporter correctly
# ---------------------------------------------------------------------------
class TestPaperBotMetricsWiring:
    def test_paper_bot_imports_metrics(self):
        """tsm_paper_trade.py must import from metrics_exporter."""
        paper_bot = BASE / "scripts" / "tsm_paper_trade.py"
        content = paper_bot.read_text(encoding="utf-8")
        assert "from quant_os.monitoring.metrics_exporter import" in content
        assert "start_metrics_server" in content

    def test_paper_bot_calls_start_metrics_server(self):
        """tsm_paper_trade.py must call start_metrics_server in main()."""
        paper_bot = BASE / "scripts" / "tsm_paper_trade.py"
        content = paper_bot.read_text(encoding="utf-8")
        assert "start_metrics_server(" in content

    def test_paper_bot_updates_metrics_after_rebalance(self):
        """run_rebalance must call metric update functions."""
        paper_bot = BASE / "scripts" / "tsm_paper_trade.py"
        content = paper_bot.read_text(encoding="utf-8")
        assert "update_drawdown(" in content
        assert "update_kill_switch(" in content
        assert "update_positions(" in content
        assert "update_heartbeat_timestamp(" in content
        assert "update_rebalance_timestamp(" in content
        assert "update_data_feed_timestamp(" in content
