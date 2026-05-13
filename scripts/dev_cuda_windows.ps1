param(
    [string]$TorchCudaIndex = "https://download.pytorch.org/whl/cu128",
    [int]$ApiPort = 8000,
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

}

Write-Host ""
Write-Host "Starting KGTraceVis FastAPI service." -ForegroundColor Green
Write-Host "API: http://127.0.0.1:$ApiPort"
Write-Host "Press Ctrl+C to stop the process."

$apiArgs = @(
    "run",
    "uvicorn",
    "kgtracevis.service.api:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$ApiPort"
)
$apiProcess = Start-Process -FilePath "uv" -ArgumentList $apiArgs -NoNewWindow -PassThru

try {
    Wait-Process -Id $apiProcess.Id
}
finally {
    if ($apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
    }
}
