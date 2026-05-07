# Test Ports Only (No Docker Commands)
$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== TESTING ALL SERVICE PORTS ===" -ForegroundColor Cyan
Write-Host ""

function Quick-TestPort($port, $timeoutMs = 2000) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $connection = $client.BeginConnect("localhost", $port, $null, $null)
        $success = $connection.AsyncWaitHandle.WaitOne($timeoutMs, $false)
        $client.Close()
        return $success
    } catch {
        return $false
    }
}

# All services to test
$services = @(
    @{Name="Redis Node 1"; Port=6379; Tier="Core"}
    @{Name="Redis Node 2"; Port=6380; Tier="Core"}
    @{Name="Redis Node 3"; Port=6381; Tier="Core"}
    @{Name="Valkey"; Port=6382; Tier="Core"}
    @{Name="ClickHouse"; Port=8123; Tier="Data"}
    @{Name="Elasticsearch"; Port=9200; Tier="Data"}
    @{Name="Typesense"; Port=8108; Tier="Data"}
    @{Name="pgvector"; Port=5433; Tier="Data"}
    @{Name="Vault"; Port=8200; Tier="Security"}
    @{Name="MinIO"; Port=9002; Tier="Security"}
    @{Name="Kong Admin"; Port=8002; Tier="Security"}
    @{Name="Kong Proxy"; Port=8001; Tier="Security"}
    @{Name="Prometheus"; Port=9090; Tier="Monitor"}
    @{Name="Grafana"; Port=3001; Tier="Monitor"}
    @{Name="Jaeger"; Port=16686; Tier="Monitor"}
    @{Name="Loki"; Port=3100; Tier="Monitor"}
    @{Name="Kafka"; Port=9092; Tier="Message"}
    @{Name="NATS"; Port=4222; Tier="Message"}
    @{Name="RabbitMQ"; Port=5672; Tier="Message"}
    @{Name="RabbitMQ Mgmt"; Port=15672; Tier="Message"}
    @{Name="API Gateway"; Port=8000; Tier="Gateway"}
    @{Name="Traefik"; Port=8080; Tier="Gateway"}
)

$passed = 0
$failed = 0
$currentTier = ""

foreach ($svc in $services) {
    if ($svc.Tier -ne $currentTier) {
        $currentTier = $svc.Tier
        Write-Host "`n[$currentTier Tier]" -ForegroundColor Yellow
    }
    
    $open = Quick-TestPort $svc.Port
    if ($open) {
        Write-Host ("  [OK] " + $svc.Name + " (Port " + $svc.Port + ")") -ForegroundColor Green
        $passed++
    } else {
        Write-Host ("  [DOWN] " + $svc.Name + " (Port " + $svc.Port + ")") -ForegroundColor Red
        $failed++
    }
}

$total = $passed + $failed
$percent = if ($total -gt 0) { [math]::Round(($passed / $total) * 100, 1) } else { 0 }

Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "Total Services: $total" -ForegroundColor White
Write-Host "Passed: $passed" -ForegroundColor Green
Write-Host "Failed: $failed" -ForegroundColor Red
Write-Host "Success Rate: $percent%" -ForegroundColor Yellow

if ($passed -eq $total) {
    Write-Host "`nALL SERVICES OPERATIONAL!" -ForegroundColor Green
} elseif ($percent -ge 80) {
    Write-Host "`nMOSTLY OPERATIONAL" -ForegroundColor Yellow
} else {
    Write-Host "`nMANY SERVICES DOWN" -ForegroundColor Red
}
