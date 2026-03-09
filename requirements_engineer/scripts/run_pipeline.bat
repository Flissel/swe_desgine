@echo off
cd /d "c:\Users\User\Desktop\Sakana-ai-research\AI-Scientist-v2"
echo Starting pipeline at %date% %time% > enterprise_output\pipeline_run4.log
python -u run_re_system.py --project re_ideas/services/whatsapp-messaging-service.json --mode enterprise >> enterprise_output\pipeline_run4.log 2>&1
echo Pipeline exited with code %ERRORLEVEL% at %date% %time% >> enterprise_output\pipeline_run4.log
