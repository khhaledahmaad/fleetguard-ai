@echo off
setlocal
rem Run from the FleetGuard repository root, with .venv activated.
rem Each directory must be new; existing datasets are never overwritten.
for %%P in (bearing-demo brake-leak-demo sensor-drift-demo axle-generator-demo wheel-slide-demo locked-axle-demo wheel-flat-demo pressure-transducer-demo brake-release-demo undemanded-brake-demo battery-depletion-demo controller-persistent-demo controller-bounded-demo) do (
    python -m fleetguard.generator --assets 2 --seed 42 --start-time 2026-01-01T06:00:00+00:00 --sampling-interval-seconds 60 --anomaly-profile %%P --output-dir data\generated\schema32-smoke\%%P
    if errorlevel 1 exit /b 1
)
echo All scenario smoke runs completed.
endlocal
