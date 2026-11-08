# TASMEEM

Open-source electronics design and simulation tools in one Docker image, opened in a browser with no terminal needed.
Included: Qucs-S, ngspice, qucsator_rf, Qucs-RFlayout, openEMS, AppCSXCAD, Octave, and the TASMEEM EM Simulator.

Team sdmay27-30, Iowa State University. Advisor: Mahmoud Gshash.

## Quick start

1. Install Docker Desktop (Mac, Windows) or Docker Engine (Linux).
2. Download this project (Code > Download ZIP) and unzip it.
3. Start the launcher for your system:

| System | Launcher |
|---|---|
| Mac | `launchers/mac/TASMEEM.command` (double-click) |
| Windows | `launchers/windows/TASMEEM.bat` (double-click) |
| Linux | `launchers/linux/tasmeem.sh` (`bash launchers/linux/tasmeem.sh`) |

The first start builds the image, which takes 30 to 60 minutes and about 30 GB of free disk. Later starts take seconds.
Your files are saved in the `work/` folder. Closing the TASMEEM browser tab stops it (after a short delay); anything saved outside `work/` is removed.

## Layout

```
Dockerfile          one image for every operating system
start.sh            starts the desktop inside the container
tasmeem-em/         TASMEEM EM Simulator (Python, openEMS)
library/            shared Qucs-S parts library
examples/           openEMS examples
launchers/          mac/  windows/  linux/
docs/               user manual
work/               your saved files (not tracked)
```

The same image runs on all systems. Only the launchers differ.
Apple Silicon Macs build a native ARM copy on first start.

## Status

Draft. Linux launcher and the combined v5 image (with the EM Simulator) are not yet tested on every system.
