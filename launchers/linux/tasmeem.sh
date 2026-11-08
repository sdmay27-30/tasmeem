#!/bin/bash
# TASMEEM launcher for Linux. Run:  bash launchers/linux/tasmeem.sh   (or double-click if your file manager allows it)
cd "$(dirname "$0")/../.." || exit 1   # repo root (Dockerfile lives here)
IMAGE=ghcr.io/sdmay27-30/tasmeem:v5
pause() { read -n 1 -s -r -p " Press any key to close."; echo; }
echo; echo " TASMEEM launcher"; echo " ----------------"

if ! command -v docker >/dev/null 2>&1; then
  echo " Docker is not installed."
  echo " Install Docker Engine or Docker Desktop for Linux: https://docs.docker.com/engine/install/"
  echo " Then run this again."
  pause; exit 1
fi

if ! docker info >/dev/null 2>&1; then
  if docker info 2>&1 | grep -qi "permission denied"; then
    echo " Docker is installed but this user is not allowed to use it."
    echo " Run once:  sudo usermod -aG docker \$USER   then log out and back in."
  else
    echo " Docker is not running. Start it with:  sudo systemctl start docker"
    echo " (Docker Desktop users: open Docker Desktop first.)"
  fi
  pause; exit 1
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo " Downloading TASMEEM (a few GB, this can take several minutes)..."
  docker pull "$IMAGE" || echo " Download failed, will try building it instead."
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  free_gb=$(df -BG --output=avail "$HOME" 2>/dev/null | tail -1 | tr -dc '0-9')
  if [ -n "$free_gb" ] && [ "$free_gb" -lt 30 ]; then
    echo; echo " Only $free_gb GB are free. About 30 GB or more is recommended for the first build."
    read -n 1 -s -r -p " Press any key to try anyway, or close this window to cancel."; echo
  fi
  echo " Building the TASMEEM image for the first time. This takes 30 to 60 minutes..."
  docker build -t "$IMAGE" . || { echo " The image build failed. Scroll up to see the error."; pause; exit 1; }
fi

mkdir -p work
docker rm -f tasmeem-app >/dev/null 2>&1
echo " Starting TASMEEM..."
if ! docker run -d --rm --name tasmeem-app -p 127.0.0.1:6080:6080 -v "$PWD/work:/home/tasmeem/work" "$IMAGE" >/dev/null; then
  echo " TASMEEM could not start. Another program may be using port 6080."
  pause; exit 1
fi

tries=0
until curl -s -f -o /dev/null http://localhost:6080/vnc.html; do
  tries=$((tries+1))
  if [ "$tries" -gt 30 ]; then
    echo " TASMEEM started but the page did not respond. Check:  docker logs tasmeem-app"
    pause; exit 1
  fi
  sleep 2
done

URL="http://localhost:6080/vnc.html?autoconnect=true&password=tasmeem&resize=scale"
if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 &
else echo " Open this address in a browser: $URL"; fi
echo; echo " TASMEEM is open in your browser."
echo " Your files are saved in the \"work\" folder in this project."
echo; echo " Keep this window open while you work."
read -n 1 -s -r -p " Press any key here when you are done to stop TASMEEM."; echo
echo " Stopping TASMEEM..."; docker stop tasmeem-app >/dev/null 2>&1
