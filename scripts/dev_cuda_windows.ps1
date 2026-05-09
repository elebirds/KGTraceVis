param(
    [string]$TorchCudaIndex = "https://download.pytorch.org/whl/cu128",
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [switch]$SkipSetup,
    [switch]$SkipCudaTorch
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Command
}

if (-not $SkipSetup) {
    Invoke-Step "Sync Python dependencies" {
        uv sync --extra dev --extra vision --extra ml
    }

    if (-not $SkipCudaTorch) {
        Invoke-Step "Install CUDA torch wheels" {
            uv pip install --index-url $TorchCudaIndex torch torchvision
        }
    }

    Invoke-Step "Install web dependencies" {
        npm --prefix web ci
    }
}

Write-Host ""
Write-Host "Starting KGTraceVis API and web frontend." -ForegroundColor Green
Write-Host "API: http://127.0.0.1:$ApiPort"
Write-Host "Web: http://127.0.0.1:$WebPort"
Write-Host "Press Ctrl+C to stop both processes."

$apiArgs = @(
    "run",
    "uvicorn",
    "kgtracevis.service.api:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$ApiPort"
)
$webArgs = @(
    "--prefix",
    "web",
    "run",
    "dev",
    "--",
    "--host",
    "127.0.0.1",
    "--port",
    "$WebPort"
)

$apiProcess = Start-Process -FilePath "uv" -ArgumentList $apiArgs -NoNewWindow -PassThru
$webProcess = Start-Process -FilePath "npm" -ArgumentList $webArgs -NoNewWindow -PassThru

try {
    Wait-Process -Id $apiProcess.Id, $webProcess.Id
}
finally {
    foreach ($process in @($apiProcess, $webProcess)) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }
}
