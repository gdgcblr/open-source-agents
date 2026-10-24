param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $AgentArgs
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$createdVenv = $false
$promptedKey = $false
$keyPointer = [IntPtr]::Zero
$previousDockerBin = $env:REPRO_CAPSULE_DOCKER_BIN

try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
        if ($pythonLauncher) {
            & $pythonLauncher.Source -3 -m venv .venv
        } else {
            $python = Get-Command python -ErrorAction SilentlyContinue
            if (-not $python) { throw 'Python 3.11+ is required. Install Python and run this command again.' }
            & $python.Source -m venv .venv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the project virtual environment.' }
        $createdVenv = $true
    }

    $isSupportedPython = & $venvPython -c 'import sys; print(sys.version_info >= (3, 11))'
    if ($LASTEXITCODE -ne 0 -or $isSupportedPython.Trim() -ne 'True') {
        throw 'Python 3.11 or newer is required. Remove .venv and retry with a supported Python installation.'
    }

    if ($AgentArgs -contains '--allow-execution') {
        Write-Host 'Preparing the Docker test runtime...'
        $docker = Get-Command docker -ErrorAction SilentlyContinue
        $dockerCandidates = @()
        if ($docker) { $dockerCandidates += $docker.Source }
        if ($env:LOCALAPPDATA) { $dockerCandidates += (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe') }
        if ($env:ProgramFiles) { $dockerCandidates += (Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe') }
        $dockerExe = $dockerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $dockerExe) {
            throw 'Docker Engine/Desktop is required for test execution. Install it, start Docker, then rerun this command.'
        }
        # Pass the resolved executable through to Python. On Windows Docker Desktop can
        # be installed correctly while its CLI directory is absent from PATH.
        $env:REPRO_CAPSULE_DOCKER_BIN = $dockerExe
        & $dockerExe info *> $null
        if ($LASTEXITCODE -ne 0) { throw 'Docker is installed but not running. Start Docker Desktop/Engine and retry.' }
        $imageTags = & $dockerExe image ls --format '{{.Repository}}:{{.Tag}}'
        if ($LASTEXITCODE -ne 0) { throw 'Could not query Docker images.' }
        if ($imageTags -notcontains 'python:3.12-slim') {
            Write-Host 'Pulling required test image python:3.12-slim...'
            & $dockerExe pull python:3.12-slim
            if ($LASTEXITCODE -ne 0) { throw 'Could not pull python:3.12-slim.' }
        }
    }

    $isInvestigation = $AgentArgs.Count -gt 0 -and $AgentArgs[0] -eq 'investigate'
    $hasApiKey = -not [string]::IsNullOrWhiteSpace($env:GEMINI_API_KEY)
    $envFile = Join-Path $projectRoot '.env'
    $dotenvHasKey = (Test-Path -LiteralPath $envFile) -and
        [bool](Select-String -LiteralPath $envFile -Pattern '^\s*GEMINI_API_KEY\s*=\s*\S+' -Quiet)
    if ($isInvestigation -and -not $hasApiKey -and -not $dotenvHasKey) {
        $secureKey = Read-Host 'Gemini API key (input hidden; used for this run only)' -AsSecureString
        if ($secureKey.Length -eq 0) { throw 'A Gemini API key is required for investigation.' }
        $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
        $env:GEMINI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
        $promptedKey = $true
    }

    $env:PYTHONPATH = Join-Path $projectRoot 'src'
    & $venvPython -m repro_capsule.cli @AgentArgs
    exit $LASTEXITCODE
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    if ($promptedKey) { Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue }
    if ($null -ne $previousDockerBin) { $env:REPRO_CAPSULE_DOCKER_BIN = $previousDockerBin }
    else { Remove-Item Env:REPRO_CAPSULE_DOCKER_BIN -ErrorAction SilentlyContinue }
    if ($keyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer) }
    if ($createdVenv) { Write-Host 'Created .venv. The agent uses Python standard-library modules only.' }
}
