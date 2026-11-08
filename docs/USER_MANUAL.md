# TASMEEM User Manual (draft)

## 1. Install Docker

TASMEEM runs inside Docker, so Docker must be installed once.

- **Mac / Windows:** install Docker Desktop from https://www.docker.com/products/docker-desktop/ and open it once.
- **Linux:** install Docker Engine from https://docs.docker.com/engine/install/ , then run `sudo usermod -aG docker $USER` and log out and back in.

## 2. Get TASMEEM

Download the project ZIP and unzip it anywhere (for example Documents). Keep the folder together.

## 3. Start TASMEEM

Double-click the launcher for your system (see the README table). A window opens and shows progress.
The first start builds the image and takes 30 to 60 minutes. Keep the computer awake and connected.
When it finishes, TASMEEM opens in your web browser as a desktop. Keep the launcher window open while you work.

## 4. Save your work

Save files in the **work** folder on the desktop. It is the `work/` folder next to the project on your computer, so files stay after TASMEEM stops.

## 5. Stop TASMEEM

Press any key in the launcher window.

## 6. Update

(To be written once the update flow is decided.)

## 7. Fixing problems

| Message | What to do |
|---|---|
| Docker is not installed / not running | Install or open Docker Desktop, wait until it says it is running, start the launcher again |
| Port 6080 in use | Close other TASMEEM windows, or restart Docker |
| Build failed or disk full | Free about 30 GB and start again |
| Windows: Docker will not start | Open PowerShell and run `wsl --update` |

## 8. EM Simulator

(Section by Ash.)
