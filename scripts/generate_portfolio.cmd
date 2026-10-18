@echo off
setlocal
pushd "%~dp0.."

python -m fleetguard.portfolio generate --seed 42 --start-time 2026-01-01T06:00:00+00:00 --sampling-interval-seconds 10 --output-dir data\generated\portfolio-v1
if errorlevel 1 goto failed
python -m fleetguard.portfolio validate --input-dir data\generated\portfolio-v1
if errorlevel 1 goto failed
python -m fleetguard.features build --input-dir data\generated\portfolio-v1 --output-dir data\features\portfolio-v1
if errorlevel 1 goto failed
python -m fleetguard.features validate --input-dir data\features\portfolio-v1
if errorlevel 1 goto failed
python -m fleetguard.audit --source-dir data\generated\portfolio-v1 --feature-dir data\features\portfolio-v1 --output-dir data\features\portfolio-v1-audit
if errorlevel 1 goto failed

popd
exit /b 0
:failed
popd
exit /b 1
