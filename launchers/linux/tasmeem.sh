#!/bin/bash
# TASMEEM launcher for Linux. Run:  bash launchers/linux/tasmeem.sh
# If Docker is missing, this offers to install it (Ubuntu/Debian). No other tools are needed.
cd "$(dirname "$0")/../.." || exit 1   # project root (Dockerfile lives here)
IMAGE=ghcr.io/sdmay27-30/tasmeem:v6
DOCKER=docker
pause() { read -n 1 -s -r -p " Press any key to close."; echo; }
echo; echo " TASMEEM launcher"; echo " ----------------"

install_docker() {
  # Only Ubuntu and Debian based systems are handled automatically.
  . /etc/os-release 2>/dev/null
  case "$ID $ID_LIKE" in
    *ubuntu*|*debian*) ;;
    *) echo " Automatic install is only set up for Ubuntu and Debian."
       echo " Install Docker from https://docs.docker.com/engine/install/ and run this again."
       return 1 ;;
  esac
  echo " Docker is needed to run TASMEEM and is not installed on this computer."
  read -r -p " Install it now? You will be asked for your password. (y/n) " ans
  case "$ans" in y|Y|yes|YES) ;; *) echo " Cancelled. TASMEEM needs Docker to run."; return 1 ;; esac
  tmp=$(mktemp)
  if command -v wget >/dev/null 2>&1; then wget -qO "$tmp" https://get.docker.com
  elif command -v curl >/dev/null 2>&1; then curl -fsSL -o "$tmp" https://get.docker.com
  else
    echo " Getting a download tool first..."
    sudo apt-get update -qq && sudo apt-get install -y -qq wget && wget -qO "$tmp" https://get.docker.com
  fi
  if [ ! -s "$tmp" ]; then echo " Could not download the Docker installer. Check the internet connection."; rm -f "$tmp"; return 1; fi
  echo " Installing Docker. This takes a few minutes..."
  sudo sh "$tmp" >/dev/null 2>&1 || { echo " The Docker install failed. Run this to see why:  sudo sh $tmp"; return 1; }
  rm -f "$tmp"
  sudo usermod -aG docker "$USER" 2>/dev/null
  sudo systemctl enable --now docker >/dev/null 2>&1
  echo " Docker is installed."
}

if ! command -v docker >/dev/null 2>&1; then
  install_docker || { pause; exit 1; }
fi

if ! docker info >/dev/null 2>&1; then
  if docker info 2>&1 | grep -qi "permission denied"; then
    # Just installed (or not yet in the docker group): use sudo for this run only.
    echo " Using administrator access for this session (your password may be asked)."
    DOCKER="sudo docker"
    if ! $DOCKER info >/dev/null 2>&1; then
      echo " Docker is installed but could not be used. Try:  sudo systemctl start docker"
      pause; exit 1
    fi
  else
    echo " Docker is not running. Trying to start it..."
    sudo systemctl start docker >/dev/null 2>&1
    sleep 3
    if ! docker info >/dev/null 2>&1 && ! sudo docker info >/dev/null 2>&1; then
      echo " Docker would not start. (Docker Desktop users: open Docker Desktop first.)"
      pause; exit 1
    fi
    docker info >/dev/null 2>&1 || DOCKER="sudo docker"
  fi
fi

if ! $DOCKER image inspect "$IMAGE" >/dev/null 2>&1; then
  echo " Downloading TASMEEM (a few GB, this can take several minutes)..."
  $DOCKER pull "$IMAGE" || echo " Download failed, will try building it instead."
fi

if ! $DOCKER image inspect "$IMAGE" >/dev/null 2>&1; then
  free_gb=$(df -BG --output=avail "$HOME" 2>/dev/null | tail -1 | tr -dc '0-9')
  if [ -n "$free_gb" ] && [ "$free_gb" -lt 30 ]; then
    echo; echo " Only $free_gb GB are free. About 30 GB or more is recommended for the first build."
    read -n 1 -s -r -p " Press any key to try anyway, or close this window to cancel."; echo
  fi
  echo " Building the TASMEEM image for the first time. This takes 30 to 60 minutes..."
  $DOCKER build -t "$IMAGE" . || { echo " The image build failed. Scroll up to see the error."; pause; exit 1; }
fi

mkdir -p work
chmod a+rwx work 2>/dev/null   # lets the container write here even if your user ID is not 1000
$DOCKER rm -f tasmeem-app >/dev/null 2>&1
echo " Starting TASMEEM..."
if ! $DOCKER run -d --rm --name tasmeem-app -p 127.0.0.1:6080:6080 -v "$PWD/work:/home/tasmeem/work" "$IMAGE" >/dev/null; then
  echo " TASMEEM could not start. Another program may be using port 6080."
  pause; exit 1
fi

# Wait until the page answers (built-in bash check, no curl needed).
tries=0
until (exec 3<>/dev/tcp/127.0.0.1/6080) 2>/dev/null; do
  tries=$((tries+1))
  if [ "$tries" -gt 30 ]; then
    echo " TASMEEM started but the page did not respond. Check:  $DOCKER logs tasmeem-app"
    pause; exit 1
  fi
  sleep 2
done
sleep 2

URL="http://localhost:6080/vnc.html?autoconnect=true&password=tasmeem&resize=scale"
if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 &
else echo " Open this address in a browser: $URL"; fi
echo; echo " TASMEEM is open in your browser."
echo " Your files are saved in the \"work\" folder in this project."
echo; echo " To stop TASMEEM: close its browser tab, or press any key here."
echo " You can close this window; TASMEEM keeps running until its browser tab is closed."
echo " Anything saved outside the work folder is removed when TASMEEM stops."
stop_tasmeem() { echo; echo " Stopping TASMEEM..."; $DOCKER stop tasmeem-app >/dev/null 2>&1; }
trap 'stop_tasmeem; exit 0' INT TERM   # Ctrl-C stops it; just closing the window does not
while [ -n "$($DOCKER ps -q -f name=tasmeem-app)" ]; do
  if read -t 2 -n 1 -s -r; then stop_tasmeem; exit 0; fi
done
echo " TASMEEM was closed. You can close this window."
