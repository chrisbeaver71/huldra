@echo off
REM ============================================================================
REM Hermes Agent V1 — Native Windows Launch
REM ============================================================================
REM Launches the Huldra Hermes agent from the permanent code tree.
REM
REM Usage:
REM   launch.cmd                    Start the gateway (default)
REM   launch.cmd gateway            Start the gateway
REM   launch.cmd cron               Start the cron scheduler
REM   launch.cmd doctor             Run diagnostics
REM   launch.cmd --help             Show help
REM
REM Prerequisites:
REM   - Python 3.11+ on PATH (or uv managing Python)
REM   - Run scripts\install.ps1 first to set up the venv
REM
REM ============================================================================

setlocal enabledelayedexpansion

set "HERMES_ROOT=%~dp0.."
set "HERMES_SOURCE=%HERMES_ROOT%\source"
set "HERMES_VENV=%HERMES_ROOT%\.venv"
set "HERMES_HOME=%LOCALAPPDATA%\hermes-huldra"

REM Use venv Python if available, else fall back to system python
if exist "%HERMES_VENV%\Scripts\python.exe" (
    set "PYTHON=%HERMES_VENV%\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

REM Ensure HERMES_HOME is set for Huldra isolation
if not defined HERMES_HOME set "HERMES_HOME=%LOCALAPPDATA%\hermes-huldra"

REM Dispatch to the requested subcommand
set "CMD=%~1"
if "%CMD%"=="" set "CMD=gateway"

REM Run from source directory
cd /d "%HERMES_SOURCE%"

echo [huldra] Hermes V1 — permanent tree launcher
echo [huldra] Source: %HERMES_SOURCE%
echo [huldra] HERMES_HOME: %HERMES_HOME%
echo [huldra] Python: %PYTHON%
echo.

"%PYTHON%" -m hermes_cli.main %*

endlocal
