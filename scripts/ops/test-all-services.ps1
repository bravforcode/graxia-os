# Test All Graxia Services
$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== TESTING ALL GRAXIA SERVICES ===" -ForegroundColor Cyan

# Function to test port
function Test-Port($port) {
    $result = Test-NetConnection -ComputerName localhost -Port $port -WarningAction SilentlyContinue
    return $result.TcpTestSucceeded
}

# Core Infrastructure
Write-Host "`n[1] Core Infrastructure (Redis Cluster + Valkey)" -ForegroundColor Yellow
$ports = @(6379, 6380, 6381, 6382)
foreach ($p in $ports) {
    $open = Test-Port $p
    if ($open) { Write-Host "  Port $p : OPEN" -ForegroundColor Green }
    else { Write-Host "  Port $p : CLOSED" -ForegroundColor Red }
}

# Data Layer
Write-Host "`n[2] Data Layer (ClickHouse, Elasticsearch, Typesense, pgvector)" -ForegroundColor Yellow
$ports = @(8123, 9200, 8108, 5433)
foreach ($p in $ports) {
    $open = Test-Port $p
    if ($open) { Write-Host "  Port $p : OPEN" -ForegroundColor Green }
    else { Write-Host "  Port $p : CLOSED" -ForegroundColor Red }
}

# Security
Write-Host "`n[3] Security (Vault, MinIO, Kong)" -ForegroundColor Yellow
$ports = @(8200, 9002, 8002, 8001)
foreach ($p in $ports) {
    $open = Test-Port $p
    if ($open) { Write-Host "  Port $p : OPEN" -ForegroundColor Green }
    else { Write-Host "  Port $p : CLOSED" -ForegroundColor Red }
}

# Monitoring
Write-Host "`n[4] Monitoring (Prometheus, Grafana, Jaeger, Loki)" -ForegroundColor Yellow
$ports = @(9090, 3001, 16686, 3100)
foreach ($p in $ports) {
    $open = Test-Port $p
    if ($open) { Write-Host "  Port $p : OPEN" -ForegroundColor Green }
    else { Write-Host "  Port $p : CLOSED" -ForegroundColor Red }
}

# Messaging
Write-Host "`n[5] Messaging (Kafka, NATS, RabbitMQ)" -ForegroundColor Yellow
$ports = @(9092, 4222, 5672, 15672)
foreach ($p in $ports) {
    $open = Test-Port $p
    if ($open) { Write-Host "  Port $p : OPEN" -ForegroundColor Green }
    else { Write-Host "  Port $p : CLOSED" -ForegroundColor Red }
}

# Gateway
Write-Host "`n[6] API Gateway (Kong, Traefik)" -ForegroundColor Yellow
$ports = @(8000, 8080)
foreach ($p in $ports) {
    $open = Test-Port $p
    if ($open) { Write-Host "  Port $p : OPEN" -ForegroundColor Green }
    else { Write-Host "  Port $p : CLOSED" -ForegroundColor Red }
}

# Application
Write-Host "`n[7] Application Services" -ForegroundColor Yellow
$ports = @(8000, 5000)
foreach ($p in $ports) {
    $open = Test-Port $p
    if ($open) { Write-Host "  Port $p : OPEN" -ForegroundColor Green }
    else { Write-Host "  Port $p : CLOSED" -ForegroundColor Red }
}

Write-Host "`n=== TEST COMPLETE ===" -ForegroundColor Cyan
