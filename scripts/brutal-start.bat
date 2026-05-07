@echo off
REM ═══════════════════════════════════════════════════════════════════════════════
REM Graxia OS — BRUTAL MODE Startup (Windows)
REM Enterprise-Grade Infrastructure with 100+ Features
REM ═══════════════════════════════════════════════════════════════════════════════

chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo ╔════════════════════════════════════════════════════════════════════════════════╗
echo ║                                                                                ║
echo ║   ██████╗ ██████╗ ██╗   ██╗████████╗ █████╗ ██╗         ███╗   ███╗ ██████╗ ███████╗
echo ║   ██╔══██╗██╔══██╗██║   ██║╚══██╔══╝██╔══██╗██║         ████╗ ████║██╔═══██╗██╔════╝
echo ║   ██████╔╝██████╔╝██║   ██║   ██║   ███████║██║         ██╔████╔██║██║   ██║█████╗
echo ║   ██╔══██╗██╔══██╗██║   ██║   ██║   ██╔══██║██║         ██║╚██╔╝██║██║   ██║██╔══╝
echo ║   ██║  ██║██████╔╝╚██████╔╝   ██║   ██║  ██║███████╗    ██║ ╚═╝ ██║╚██████╔╝██║
echo ║   ╚═╝  ╚═╝╚═════╝  ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚══════╝    ╚═╝     ╚═╝ ╚═════╝ ╚═╝
echo ║                                                                                ║
echo ║   Enterprise Infrastructure with 100+ Features                                ║
echo ╚════════════════════════════════════════════════════════════════════════════════╝
echo.

REM Check .env
if not exist ".env" (
    echo [ERROR] .env not found!
    echo Please run: copy .env.example .env and configure it
    pause
    exit /b 1
)

REM Check Docker
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not running!
    echo Please start Docker Desktop first.
    pause
    exit /b 1
)

REM Check system resources
echo [INFO] Checking system resources...
for /f "tokens=*" %%a in ('wmic computersystem get TotalPhysicalMemory /value ^| find "="') do (
    for /f "tokens=2 delims==" %%b in ("%%a") do (
        set "total_ram=%%b"
        set /a ram_gb=%%b / 1024 / 1024 / 1024
    )
)
echo [INFO] Total RAM: !ram_gb! GB

if !ram_gb! LSS 8 (
    echo [WARNING] Recommended RAM: 8GB+ for Brutal Mode
    echo [WARNING] Current RAM: !ram_gb! GB - Performance may be limited
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 1
)

echo.
echo [INFO] Starting BRUTAL MODE infrastructure...
echo [INFO] This will start 30+ services including:
echo        - Redis Cluster (3 nodes) + Valkey
echo        - ClickHouse Analytics (OLAP)
echo        - Elasticsearch + Typesense Search
echo        - Prometheus + Grafana + Loki + Jaeger
echo        - NATS + RabbitMQ Messaging
echo        - Kafka + Zookeeper Streaming
echo        - MinIO S3 Data Lake
echo        - Vault Secrets Management
echo        - Kong API Gateway
echo        - API Server (2 replicas)
echo        - Celery Workers + Scheduler
echo        - 100%% of all 100 Features!
echo.

REM Create necessary directories
echo [INFO] Creating directories...
if not exist "logs" mkdir logs
if not exist "backups" mkdir backups
if not exist "infrastructure\monitoring\grafana\dashboards" mkdir infrastructure\monitoring\grafana\dashboards
if not exist "infrastructure\monitoring\grafana\datasources" mkdir infrastructure\monitoring\grafana\datasources
if not exist "infrastructure\clickhouse" mkdir infrastructure\clickhouse
if not exist "infrastructure\vault" mkdir infrastructure\vault
if not exist "infrastructure\kong" mkdir infrastructure\kong
if not exist "ml_models" mkdir ml_models

echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo Phase 1: Infrastructure Services
echo ════════════════════════════════════════════════════════════════════════════════
echo.

REM Start infrastructure services first
docker compose -f docker-compose.brutal.yml up -d redis-node-1 redis-node-2 redis-node-3
if errorlevel 1 (
    echo [ERROR] Failed to start Redis Cluster
    pause
    exit /b 1
)

echo [INFO] Waiting for Redis Cluster to initialize...
timeout /t 5 /nobreak >nul

REM Setup Redis Cluster (one-time)
echo [INFO] Setting up Redis Cluster...
docker compose -f docker-compose.brutal.yml --profile setup run --rm redis-cluster-setup 2>nul
if errorlevel 1 (
    echo [WARNING] Redis Cluster setup may have already been run
)

echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo Phase 2: Analytics, Storage & Security Services
echo ════════════════════════════════════════════════════════════════════════════════
echo.

docker compose -f docker-compose.brutal.yml up -d clickhouse elasticsearch typesense valkey vault minio
if errorlevel 1 (
    echo [ERROR] Failed to start analytics/security services
    pause
    exit /b 1
)

echo [INFO] Waiting for Vault, MinIO and analytics services...
timeout /t 15 /nobreak >nul

REM Setup MinIO buckets (one-time)
echo [INFO] Setting up MinIO buckets...
docker compose -f docker-compose.brutal.yml --profile setup run --rm minio-setup 2>nul
if errorlevel 1 (
    echo [WARNING] MinIO setup may have already been run
)

echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo Phase 3: Monitoring Stack
echo ════════════════════════════════════════════════════════════════════════════════
echo.

docker compose -f docker-compose.brutal.yml up -d prometheus grafana loki jaeger
if errorlevel 1 (
    echo [ERROR] Failed to start monitoring
    pause
    exit /b 1
)

echo [INFO] Waiting for monitoring stack...
timeout /t 5 /nobreak >nul

echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo Phase 4: Messaging & Streaming Services
echo ════════════════════════════════════════════════════════════════════════════════
echo.

docker compose -f docker-compose.brutal.yml up -d zookeeper kafka kafka-connect nats rabbitmq
if errorlevel 1 (
    echo [ERROR] Failed to start messaging/streaming services
    pause
    exit /b 1
)

echo [INFO] Waiting for Kafka and messaging services...
timeout /t 15 /nobreak >nul

echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo Phase 5: API Gateway
echo ════════════════════════════════════════════════════════════════════════════════
echo.

docker compose -f docker-compose.brutal.yml up -d kong-database kong
if errorlevel 1 (
    echo [ERROR] Failed to start API Gateway
    pause
    exit /b 1
)

echo [INFO] Setting up Kong migrations (if needed)...
docker compose -f docker-compose.brutal.yml --profile setup run --rm kong-migration 2>nul
docker compose -f docker-compose.brutal.yml restart kong 2>nul

echo [INFO] Waiting for Kong to be ready...
timeout /t 10 /nobreak >nul

echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo Phase 6: Core Application Services
echo ════════════════════════════════════════════════════════════════════════════════
echo.

docker compose -f docker-compose.brutal.yml up -d api worker beat event-processor
if errorlevel 1 (
    echo [ERROR] Failed to start application services
    pause
    exit /b 1
)

echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo Phase 6: Health Checks
echo ════════════════════════════════════════════════════════════════════════════════
echo.

echo [INFO] Running health checks...
timeout /t 15 /nobreak >nul

REM Check API health
curl -sf http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [WARNING] API health check failed - may still be starting
) else (
    echo [OK] API is healthy
)

REM Check Redis
docker exec graxia-redis-1 redis-cli ping >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Redis health check failed
) else (
    echo [OK] Redis Cluster is healthy
)

REM Check ClickHouse
curl -sf http://localhost:8123/ping >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ClickHouse health check failed
) else (
    echo [OK] ClickHouse is healthy
)

REM Check Vault
curl -sf http://localhost:8200/v1/sys/health >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Vault health check failed
) else (
    echo [OK] Vault is healthy
)

REM Check Kafka
docker exec graxia-kafka kafka-broker-api-versions --bootstrap-server localhost:9092 >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Kafka health check failed
) else (
    echo [OK] Kafka is healthy
)

REM Check Kong
curl -sf http://localhost:8002/status >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Kong health check failed
) else (
    echo [OK] Kong API Gateway is healthy
)

echo.
echo ╔════════════════════════════════════════════════════════════════════════════════╗
echo ║                      BRUTAL MODE IS RUNNING!                                  ║
echo ╚════════════════════════════════════════════════════════════════════════════════╝
echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo Services:
echo ════════════════════════════════════════════════════════════════════════════════
echo.
echo 🌐 Application:
echo    API:        http://localhost:8000
echo    API Docs:   http://localhost:8000/docs
echo    Kong GW:    http://localhost:8001  (Proxy)
echo    Kong Admin: http://localhost:8002  (Admin API)
echo    Traefik:    http://localhost:8080
echo.
echo 📊 Monitoring:
echo    Grafana:    http://localhost:3001  (admin/graxia_admin_2024)
echo    Prometheus: http://localhost:9090
echo    Jaeger:     http://localhost:16686
echo.
echo 💾 Data & Storage:
echo    ClickHouse: http://localhost:8123  (graxia/graxia_secure_2024)
echo    Elastic:    http://localhost:9200
echo    Typesense:  http://localhost:8108  (graxia_typesense_key_2024)
echo    Redis:      localhost:6379,6380,6381 (Cluster)
echo    MinIO:      http://localhost:9001  (graxiaadmin/graxiaadmin2024)
echo    MinIO API:  http://localhost:9002
echo    pgvector:   localhost:5433
echo.
echo 🔐 Security:
echo    Vault:      http://localhost:8200  (graxia-vault-root-2024)
echo.
echo 📨 Messaging:
echo    NATS:       nats://localhost:4222
echo    RabbitMQ:   http://localhost:15672 (graxia/graxia_mq_2024)
echo    Kafka:      localhost:9092
echo    Kafka Conn: http://localhost:8083
echo.
echo ════════════════════════════════════════════════════════════════════════════════
echo Commands:
echo ════════════════════════════════════════════════════════════════════════════════
echo.
echo View logs:    docker compose -f docker-compose.brutal.yml logs -f [service]
echo Stop all:     docker compose -f docker-compose.brutal.yml down
echo Restart:      docker compose -f docker-compose.brutal.yml restart [service]
echo Scale API:    docker compose -f docker-compose.brutal.yml up -d --scale api=3
echo.
echo ⚠️  TRADING MODE: Check .env for TRADING_MODE setting
echo.

choice /C YN /M "Open dashboard in browser"
if errorlevel 2 goto :end
if errorlevel 1 start http://localhost:8000/docs

:end
echo.
echo Press any key to exit...
pause >nul
