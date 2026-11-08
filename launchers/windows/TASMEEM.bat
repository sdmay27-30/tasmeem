@echo off
setlocal
title TASMEEM launcher
cd /d "%~dp0..\.."
rem v6 = v5 plus: the container stops when the browser tab is closed
set IMAGE=ghcr.io/sdmay27-30/tasmeem:v6
echo.
echo  TASMEEM launcher
echo  ----------------

where docker >nul 2>&1
if errorlevel 1 goto nodocker

docker info >nul 2>&1
if not errorlevel 1 goto dockerready
echo  Starting Docker Desktop. This can take a minute...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set tries=0
:waitdocker
set /a tries+=1
if %tries% GTR 60 goto dockertimeout
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if errorlevel 1 goto waitdocker
:dockerready

docker image inspect %IMAGE% >nul 2>&1
if not errorlevel 1 goto imageready
echo  Downloading TASMEEM (a few GB, this can take several minutes)...
docker pull %IMAGE%
docker image inspect %IMAGE% >nul 2>&1
if not errorlevel 1 goto imageready
echo  Download failed, will try building it instead.
if not exist Dockerfile goto noimage
rem Low disk space on C: can crash Docker during the build, so warn first.
set freegb=999
for /f "tokens=1 delims=.," %%a in ('powershell -NoProfile -Command "$d=Get-PSDrive C; $d.Free/1GB" 2^>nul') do set freegb=%%a
if %freegb% GEQ 30 goto diskok
echo.
echo  Only %freegb% GB are free on drive C. About 30 GB or more is recommended for the first build.
echo  Low disk space can make the build fail. Free up space first if you can.
echo  Press any key to try anyway, or close this window to cancel.
pause >nul
:diskok
echo  Building the TASMEEM image for the first time. This takes 30 to 60 minutes (Qucs-S, openEMS and RF Layout are compiled)...
docker build -t %IMAGE% .
if errorlevel 1 goto buildfail
:imageready

if not exist work mkdir work
docker rm -f tasmeem-app >nul 2>&1
echo  Starting TASMEEM...
docker run -d --rm --name tasmeem-app -p 127.0.0.1:6080:6080 -v "%cd%\work:/home/tasmeem/work" %IMAGE% >nul
if errorlevel 1 goto runfail

set tries=0
:waitpage
set /a tries+=1
if %tries% GTR 30 goto pagetimeout
curl.exe -s -f -o nul http://localhost:6080/vnc.html
if not errorlevel 1 goto pageready
timeout /t 2 /nobreak >nul
goto waitpage
:pageready

start "" "http://localhost:6080/vnc.html?autoconnect=true&password=tasmeem&resize=scale"
echo.
echo  TASMEEM is open in your browser.
echo  Your files are saved in the "work" folder next to this launcher.
echo.
echo  To stop TASMEEM: close its browser tab, or press S here.
echo  You can close this window; TASMEEM keeps running until its browser tab is closed.
echo  Anything saved outside the work folder is removed when TASMEEM stops.
:waitloop
docker ps -q -f name=tasmeem-app | findstr . >nul
if errorlevel 1 goto closed
choice /c SN /t 2 /d N /n >nul
if errorlevel 2 goto waitloop
echo  Stopping TASMEEM...
docker stop tasmeem-app >nul 2>&1
exit /b 0
:closed
echo  TASMEEM was closed. You can close this window.
pause
exit /b 0

:nodocker
echo  Docker Desktop is not installed.
echo  Opening the download page now. Install it, start it once, then run this again.
start "" "https://www.docker.com/products/docker-desktop/"
pause
exit /b 1
:dockertimeout
echo  Docker did not start in time. Open Docker Desktop yourself, wait until it says it is running, then run this again.
echo  If it keeps failing, update Windows Subsystem for Linux: open PowerShell and run   wsl --update
pause
exit /b 1
:noimage
echo  The TASMEEM image was not found and there is no Dockerfile in this folder to build it.
pause
exit /b 1
:buildfail
echo  The image build failed. Scroll up to see the error.
pause
exit /b 1
:runfail
echo  TASMEEM could not start. Another program may be using port 6080.
pause
exit /b 1
:pagetimeout
echo  TASMEEM started but the page did not respond. Try again, or check Docker Desktop for the container logs.
pause
exit /b 1
