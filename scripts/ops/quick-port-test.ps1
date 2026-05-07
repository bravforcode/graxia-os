# Quick Port Test with Short Timeout
$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== QUICK PORT TEST (2 sec timeout per port) ===" -ForegroundColor Cyan

function Quick-TestPort($port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $connection = $client.BeginConnect("localhost", $port, $null, $null)
        $success = $connection.AsyncWaitHandle.WaitOne(2000, $false)
        if ($success) { 
            $client.Close()
            return $true 
        }
        $client.Close()
        return $false
    } catch {
        return $false
    }
}

# Test all ports
$allPorts = @(
    @{Port=6379; Service="Redis Node 1"; Tier="Core"},
    @{Port=6380; Service="Redis Node 2"; Tier="Core"},
    @{Port=6381; Service="Redis Node 3"; Tier="Core"},
    @{Port=6382; Service="Valkey"; Tier="Core"},
    @{Port=8123; Service="ClickHouse"; Tier="Data"},
    @{Port=9200; Service="Elasticsearch"; Tier="Data"},
    @{Port=8108; Service="Typesense"; Tier="Data"},
    @{Port=5433; Service="pgvector"; Tier="Data"},
    @{Port=8200; Service="Vault"; Tier="Security"},
    @{Port=9002; Service="MinIO"; Tier="Security"},
    @{Port=8002; Service="Kong Admin"; Tier="Security"},
    @{Port=8001; Service="Kong Proxy"; Tier="Security"},
    @{Port=9090; Service="Prometheus"; Tier="Monitor"},
    @{Port=3001; Service="Grafana"; Tier="Monitor"},
    @{Port=16686; Service="Jaeger"; Tier="Monitor"},
    @{Port=3100; Service="Loki"; Tier="Monitor"},
    @{Port=9092; Service="Kafka"; Tier="Message"},
    @{Port=4222; Service="NATS"; Tier="Message"},
    @{Port=5672; Service="RabbitMQ"; Tier="Message"},
    @{Port=15672; Service="RabbitMQ Mgmt"; Tier="Message"},
    @{Port=8000; Service="API Gateway"; Tier="Gateway"},
    @{Port=8080; Service="Traefik"; Tier="Gateway"}
)

$passed = 0
$failed = 0

foreach ($svc in $allPorts) {
    $open = Quick-TestPort $svc.Port
    $status = if ($open) { "OPEN" } else { "CLOSED" }
    $color = if ($open) { "Green" } else { "Red" }
    Write-Host ("[" + $svc.Tier + "] " + $svc.Service + " (Port " + $svc.Port + "): " + $status) -ForegroundColor $color
    if ($open) { $passed++ } else { $failed++ }
}

Write-Host "`n=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "Passed: $passed / $($allPorts.Count)" -ForegroundColor Green
Write-Host "Failed: $failed / $($allPorts.Count)" -ForegroundColor Red
$percent = [math]::Round(($passed / $allPorts.Count) * 100, 1)
Write-Host "Success Rate: $percent%" -ForegroundColor Yellow
