@echo off
setlocal
cd /d "%~dp0.."
py scripts\gen_puml_from_spec.py temp\spec.json temp
exit /b %ERRORLEVEL%
