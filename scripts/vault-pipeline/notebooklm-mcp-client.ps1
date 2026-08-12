# notebooklm-mcp-client.ps1 — MCP client for NotebookLM
# Creates notebooks and adds sources via JSON-RPC over stdio

param(
    [string]$Action,  # "create-notebook", "add-source", "list-notebooks", "ask-question"
    [string]$NotebookName,
    [string]$NotebookDesc,
    [string]$SourceText,
    [string]$SourceTitle,
    [string]$Question
)

$ErrorActionPreference = "Stop"

function Send-MCPRequest {
    param($Process, $Method, $Params = @{})

    $request = @{
        jsonrpc = "2.0"
        id = [System.Threading.Interlocked]::Increment([ref]$script:requestId)
        method = $Method
        params = $Params
    } | ConvertTo-Json -Depth 10 -Compress

    $request | Out-File -FilePath "$env:TEMP\notebooklm_req.json" -Encoding utf8

    $stdin = $Process.StandardInput
    $stdin.WriteLine($request)
    $stdin.Flush()

    Start-Sleep -Milliseconds 500

    $output = $Process.StandardOutput.ReadLine()
    return $output
}

# Start MCP server
$script:requestId = 0
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "npx"
$psi.Arguments = "-y notebooklm-mcp@latest"
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true

$proc = [System.Diagnostics.Process]::Start($psi)
Start-Sleep -Seconds 3

switch ($Action) {
    "list-notebooks" {
        $result = Send-MCPRequest -Process $proc -Method "tools/call" -Params @{
            name = "list_notebooks"
            arguments = @{}
        }
        Write-Output $result
    }
    "create-notebook" {
        $result = Send-MCPRequest -Process $proc -Method "tools/call" -Params @{
            name = "add_notebook"
            arguments = @{
                name = $NotebookName
                description = $NotebookDesc
            }
        }
        Write-Output $result
    }
    "add-source" {
        $result = Send-MCPRequest -Process $proc -Method "tools/call" -Params @{
            name = "add_source"
            arguments = @{
                notebook_name = $NotebookName
                source_type = "text"
                text = $SourceText
                title = $SourceTitle
            }
        }
        Write-Output $result
    }
    "ask-question" {
        $result = Send-MCPRequest -Process $proc -Method "tools/call" -Params @{
            name = "ask_question"
            arguments = @{
                notebook_name = $NotebookName
                question = $Question
            }
        }
        Write-Output $result
    }
}

$proc.Kill()
