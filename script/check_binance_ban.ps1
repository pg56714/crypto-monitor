param(
    [string]$Url = "https://fapi.binance.com/fapi/v1/time"
)

$ErrorActionPreference = "Stop"

function Format-Duration {
    param([int]$Seconds)

    $span = [TimeSpan]::FromSeconds($Seconds)
    if ($span.TotalDays -ge 1) {
        return "{0}d {1}h {2}m {3}s" -f [int]$span.TotalDays, $span.Hours, $span.Minutes, $span.Seconds
    }
    if ($span.TotalHours -ge 1) {
        return "{0}h {1}m {2}s" -f [int]$span.TotalHours, $span.Minutes, $span.Seconds
    }
    if ($span.TotalMinutes -ge 1) {
        return "{0}m {1}s" -f [int]$span.TotalMinutes, $span.Seconds
    }
    return "{0}s" -f [int]$span.TotalSeconds
}

function Get-RetryAfterSeconds {
    param($Headers)

    $value = $Headers["Retry-After"]
    if (-not $value) {
        return $null
    }

    $seconds = 0
    if ([int]::TryParse([string]$value, [ref]$seconds)) {
        return $seconds
    }

    $retryAt = [DateTimeOffset]::MinValue
    if ([DateTimeOffset]::TryParse([string]$value, [ref]$retryAt)) {
        $remaining = [int][Math]::Ceiling(($retryAt - [DateTimeOffset]::UtcNow).TotalSeconds)
        return [Math]::Max(0, $remaining)
    }

    return $null
}

try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing
    Write-Output "status=OK"
    Write-Output "http_status=$($response.StatusCode)"
    Write-Output "retry_after_seconds="
    Write-Output "retry_after_human="
    exit 0
} catch {
    $response = $_.Exception.Response
    if (-not $response) {
        Write-Output "status=ERROR"
        Write-Output "message=$($_.Exception.Message)"
        exit 1
    }

    $statusCode = [int]$response.StatusCode
    $retryAfterSeconds = Get-RetryAfterSeconds -Headers $response.Headers
    $retryAfterHuman = if ($null -ne $retryAfterSeconds) {
        Format-Duration -Seconds $retryAfterSeconds
    } else {
        ""
    }

    if ($statusCode -eq 418) {
        Write-Output "status=BANNED"
    } elseif ($statusCode -eq 429) {
        Write-Output "status=RATE_LIMITED"
    } else {
        Write-Output "status=HTTP_ERROR"
    }

    Write-Output "http_status=$statusCode"
    Write-Output "retry_after_seconds=$retryAfterSeconds"
    Write-Output "retry_after_human=$retryAfterHuman"

    if ($null -eq $retryAfterSeconds) {
        Write-Output "note=Retry-After header not present; exact remaining time is unknown."
    }

    exit 0
}
