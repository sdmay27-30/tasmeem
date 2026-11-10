# TASMEEM

Open-source electronics design and simulation tools in one Docker image, opened in a browser with no terminal needed.
Included: Qucs-S, ngspice, qucsator_rf, Qucs-RFlayout, openEMS, AppCSXCAD, Octave, and the TASMEEM EM Simulator.

Team sdmay27-30, Iowa State University. Advisor: Mahmoud Gshash.

## Quick start

You do not build anything. GitHub already builds the image (`ghcr.io/sdmay27-30/tasmeem`) and the launcher downloads it for you.

1. Install Docker Desktop (Mac, Windows) or Docker Engine (Linux). On Linux, the launcher offers to install Docker for you (Ubuntu and Debian).
2. Download this project (Code > Download ZIP) and unzip it.
3. Start the launcher for your system:

| System | Launcher |
|---|---|
| Mac | `launchers/mac/TASMEEM.command` (double-click) |
| Windows | `launchers/windows/TASMEEM.bat` (double-click) |
| Linux | `launchers/linux/tasmeem.sh` (`bash launchers/linux/tasmeem.sh`) |

The first start downloads the image (about 1.3 GB), takes about 2 minutes, and needs about 10 GB of free disk. Later starts take seconds.

**Do not run `docker build`.** If you see a build error, a build command was run by mistake. Close that window and use the launcher above instead.

Mac and Windows show a warning the first time you open a downloaded launcher (Mac: Open Anyway in System Settings > Privacy & Security; Windows: Run). The user manual has the steps with screenshots.

## Your files and stopping

Your files are saved in the `work/` folder. Anything saved outside `work/` is removed.
To stop TASMEEM, press a key in the launcher window (S on Windows), or close the TASMEEM browser tab, which stops it after about 2 minutes. Closing the launcher window alone does not stop it.

## User manual

- [User manual](docs/USER_MANUAL.md): install, launch, and troubleshooting for Mac, Windows and Linux
- [Qucs-S guide](docs/tools/qucs-s.md)
- [RF Layout guide](docs/tools/rf-layout.md)

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

The same image runs on all systems. Only the launchers differ. The image is published for Intel/AMD and Apple Silicon, and Docker picks the right one.

## Adding a tool (developers)

Work on a branch and build a test image with a test tag (for example `v7-aaron`). Only the person testing it uses that tag. Students stay on the current release until a plain version tag (for example `v7`) is published and the launchers are pointed at it.

## Status

Tested on Mac (Apple Silicon), Windows 10 and 11, and Ubuntu Linux (ARM64 and x86_64 virtual machines, plus a teammate's own Linux computer). On each, all the tools open, files save, and both ways to stop work.

Not tested yet: Intel Macs and Linux systems other than Ubuntu.
