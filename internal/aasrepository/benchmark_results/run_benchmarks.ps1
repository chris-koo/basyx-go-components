param(
    [int]$TotalPosts = 100000,
    [int]$ProgressEvery = 5000,
    [string]$ComposeCommand = "docker compose"
)

$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResultsDir = Join-Path $ScriptRoot "results"
if (-not (Test-Path $ResultsDir)) {
    New-Item -ItemType Directory -Path $ResultsDir | Out-Null
}

function Invoke-BenchmarkScenario {
    param(
        [Parameter(Mandatory = $true)][string]$Scenario,
        [Parameter(Mandatory = $true)][int]$ScenarioTotalPosts,
        [Parameter(Mandatory = $true)][int]$ScenarioProgressEvery,
        [Parameter(Mandatory = $true)][string]$ScenarioComposeCommand
    )

    $env:BENCH_SCENARIOS = $Scenario
    $env:BENCH_TOTAL_POSTS = "$ScenarioTotalPosts"
    $env:BENCH_PROGRESS_EVERY = "$ScenarioProgressEvery"

    Write-Host "Running scenario '$Scenario' with $ScenarioTotalPosts requests..."
    Invoke-Expression "$ScenarioComposeCommand -f docker_compose/docker_compose.yml --profile benchmark up --build --abort-on-container-exit aas_repository_benchmark_runner"

    Write-Host "Resetting compose stack and database volumes..."
    Invoke-Expression "$ScenarioComposeCommand -f docker_compose/docker_compose.yml down -v"
}

try {
    Write-Host "Starting full benchmark run (minimal -> complex)."
    Invoke-BenchmarkScenario -Scenario "minimal" -ScenarioTotalPosts $TotalPosts -ScenarioProgressEvery $ProgressEvery -ScenarioComposeCommand $ComposeCommand
    Invoke-BenchmarkScenario -Scenario "complex" -ScenarioTotalPosts $TotalPosts -ScenarioProgressEvery $ProgressEvery -ScenarioComposeCommand $ComposeCommand
    Write-Host "Both benchmark scenarios completed."
}
catch {
    Write-Error "Benchmark run failed: $($_.Exception.Message)"
    Write-Host "Attempting compose cleanup..."
    try {
        Invoke-Expression "$ComposeCommand -f docker_compose/docker_compose.yml down -v"
    }
    catch {
        Write-Warning "Compose cleanup also failed: $($_.Exception.Message)"
    }
    exit 1
}
