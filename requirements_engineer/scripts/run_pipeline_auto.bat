@echo off
setlocal enabledelayedexpansion
cd /d "c:\Users\User\Desktop\Sakana-ai-research\AI-Scientist-v2"

set PROJECT=re_ideas/services/whatsapp-messaging-service.json
set LOG=enterprise_output\pipeline_auto.log
set MAX_RETRIES=5
set RETRY=0

echo ============================================== > %LOG%
echo Auto-restart pipeline with checkpoints >> %LOG%
echo Started: %date% %time% >> %LOG%
echo ============================================== >> %LOG%

:run
set /a RETRY+=1
echo. >> %LOG%
echo [Attempt %RETRY%/%MAX_RETRIES%] Starting at %date% %time% >> %LOG%

REM Find the latest output directory for this project
set RESUME_DIR=
for /f "delims=" %%d in ('dir /b /ad /o-d "enterprise_output\whatsapp-messaging-service_*" 2^>nul') do (
    if not defined RESUME_DIR (
        REM Check if _checkpoints dir exists in this output
        if exist "enterprise_output\%%d\_checkpoints" (
            set RESUME_DIR=enterprise_output\%%d
        )
    )
)

if defined RESUME_DIR (
    echo [RESUME] Found checkpoint dir: %RESUME_DIR% >> %LOG%
    python -u run_re_system.py --project %PROJECT% --mode enterprise --resume %RESUME_DIR% >> %LOG% 2>&1
) else (
    echo [FRESH] No checkpoint dir found, starting fresh >> %LOG%
    python -u run_re_system.py --project %PROJECT% --mode enterprise >> %LOG% 2>&1
)

set EXIT_CODE=%ERRORLEVEL%
echo [EXIT] Code: %EXIT_CODE% at %date% %time% >> %LOG%

if %EXIT_CODE% EQU 0 (
    echo [SUCCESS] Pipeline completed successfully! >> %LOG%
    goto :done
)

if %RETRY% GEQ %MAX_RETRIES% (
    echo [FAIL] Max retries reached. Giving up. >> %LOG%
    goto :done
)

echo [CRASH] Pipeline crashed. Restarting from checkpoint in 10s... >> %LOG%
timeout /t 10 /nobreak >nul
goto :run

:done
echo ============================================== >> %LOG%
echo Finished: %date% %time% >> %LOG%
echo ============================================== >> %LOG%
