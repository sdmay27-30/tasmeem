#!/bin/bash
# TASMEEM launcher for Mac. Double-click to start.
cd "$(dirname "$0")/../.." || exit 1   # repo root (Dockerfile lives here)
IMAGE=ghcr.io/sdmay27-30/tasmeem:v6   # v6 = v5 plus: the container stops when the browser tab is closed
echo
echo " TASMEEM launcher"
echo " ----------------"

if ! command -v docker >/dev/null 2>&1; then
  echo " Docker Desktop is not installed."
  if [ "$(uname -m)" = "arm64" ]; then
    echo " This Mac has an Apple chip: choose the Apple Silicon version."
  else
    echo " This Mac has an Intel chip: choose the Intel version."
  fi
  echo " Opening the download page now. Install it, start it once, then run this again."
  open "https://www.docker.com/products/docker-desktop/"
  read -n 1 -s -r -p " Press any key to close."; exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo " Starting Docker Desktop. This can take a minute..."
  open -a Docker
  tries=0
  until docker info >/dev/null 2>&1; do
    tries=$((tries+1))
    if [ "$tries" -gt 60 ]; then
      echo " Docker did not start in time. Open Docker Desktop yourself, then run this again."
      read -n 1 -s -r -p " Press any key to close."; exit 1
    fi
    sleep 3
  done
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo " Downloading TASMEEM (a few GB, this can take several minutes)..."
  docker pull "$IMAGE" || echo " Download failed, will try building it instead."
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  if [ -f Dockerfile ]; then
    # Low disk space can crash Docker during the build, so warn first.
    free_gb=$(df -g "$HOME" 2>/dev/null | awk 'NR==2{print $4}')
    if [ -n "$free_gb" ] && [ "$free_gb" -lt 30 ] 2>/dev/null; then
      echo
      echo " Only $free_gb GB are free on this Mac. About 30 GB or more is recommended for the first build."
      echo " Low disk space can make the build fail. Free up space first if you can."
      read -n 1 -s -r -p " Press any key to try anyway, or close this window to cancel."
      echo
    fi
    echo " Building the TASMEEM image for the first time. This takes 30 to 60 minutes (Qucs-S, openEMS and RF Layout are compiled)..."
    docker build -t "$IMAGE" . || { echo " The image build failed. Scroll up to see the error."; read -n 1 -s -r -p " Press any key to close."; exit 1; }
  else
    echo " The TASMEEM image was not found and there is no Dockerfile in this folder."
    read -n 1 -s -r -p " Press any key to close."; exit 1
  fi
fi

mkdir -p work
docker rm -f tasmeem-app >/dev/null 2>&1
echo " Starting TASMEEM..."
if ! docker run -d --rm --name tasmeem-app -p 127.0.0.1:6080:6080 -v "$PWD/work:/home/tasmeem/work" "$IMAGE" >/dev/null; then
  echo " TASMEEM could not start. Another program may be using port 6080."
  read -n 1 -s -r -p " Press any key to close."; exit 1
fi

tries=0
until curl -s -f -o /dev/null http://localhost:6080/vnc.html; do
  tries=$((tries+1))
  if [ "$tries" -gt 30 ]; then
    echo " TASMEEM started but the page did not respond. Check Docker Desktop for the container logs."
    read -n 1 -s -r -p " Press any key to close."; exit 1
  fi
  sleep 2
done

open "http://localhost:6080/vnc.html?autoconnect=true&password=tasmeem&resize=scale"
echo
echo " TASMEEM is open in your browser."
echo " Your files are saved in the \"work\" folder next to this launcher."
echo
echo " To stop TASMEEM: close its browser tab, or press any key here."
echo " You can close this window; TASMEEM keeps running until its browser tab is closed."
echo " Anything saved outside the work folder is removed when TASMEEM stops."
stop_tasmeem() { echo; echo " Stopping TASMEEM..."; docker stop tasmeem-app >/dev/null 2>&1; }
trap 'stop_tasmeem; exit 0' INT TERM   # Ctrl-C stops it; just closing the window does not
while [ -n "$(docker ps -q -f name=tasmeem-app)" ]; do
  if read -t 2 -n 1 -s -r; then stop_tasmeem; exit 0; fi
done
echo " TASMEEM was closed. You can close this window."
