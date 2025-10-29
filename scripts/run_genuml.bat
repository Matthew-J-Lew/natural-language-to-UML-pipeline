@echo off
setlocal
rem Go to repo root (scripts\..)
cd /d "%~dp0.."

rem Generate UML into the temp folder
py scripts\gen_uml_from_spec.py temp\spec.json scripts\template.uml.tpl temp

rem Propagate Python's exit code (should be 0 if OK)
exit /b %ERRORLEVEL%
