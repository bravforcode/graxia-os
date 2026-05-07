$ErrorActionPreference = "Stop"

# ตั้งค่า TestSprite API Key สำหรับรันเซิร์ฟเวอร์ MCP เพื่อทดสอบระบบแบบอัตโนมัติ
$env:API_KEY = "sk-user-AhUK-RlfQPbWxzKt9a2O3Z5zv2XY6YzVGfpqxdIZQmhbH1KXFLiikWULV1wNsTA0vnMco7T8N8gc9_DHy04mu3puPDtEciRuCxqfLORXy5S2OF-2tCjBuYY1WRLYEI71BHE"

Write-Host "Starting TestSprite MCP Server for Graxia OS..."
npx -y @testsprite/testsprite-mcp@latest
