"""
Market data recording and health monitoring for Quant OS

- TickRecorder: Tick recording with quality checks
- TickStore: Tick persistence as JSONL files
- SpreadMonitor: Spread baseline and anomaly detection
- FeedHealthMonitor: Real-time feed health tracking
- ClockGuard: Clock drift detection
- MarketSessionGuard: Market open/close determination
- DataWatermark: Data freshness tracking
- AccountSnapshot: Redacted account snapshots
- SmokeReport: Diagnostic report generation
- MarketHealthMachine: Central health state machine
"""
