# TASMEEM image, step 1: prove a desktop + Qucs-S works in a browser.
# Step 2: add openEMS (EM simulation) with its 3D viewer and Octave/Python.
# Step 3: add Qucs-RFlayout (microstrip schematic to KiCad layout / openEMS script).
# Step 4: add the font Octave needs to draw plots.
# Step 5: add the TASMEEM EM Simulator app (point-and-click openEMS front end, Python).
# ---------------- Stage 1: build Qucs-RFlayout (kept out of the final image) ----------------
# Qucs-RFlayout turns a Qucs-S microstrip schematic into a KiCad layout or an openEMS script.
# It needs LaTeX and the Lato font only while compiling, so it is built in its own stage and only
# the finished program is copied into the final image (keeps the image smaller).
FROM ubuntu:24.04 AS rflayout-build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git build-essential cmake \
    qt6-base-dev libqt6opengl6-dev libgl1-mesa-dev libglx-dev \
    texlive-xetex fonts-lato \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --branch 2.1.2 --depth 1 https://github.com/thomaslepoix/Qucs-RFlayout.git /src \
 && cd /src \
 && cmake -S. -Bbuild -DCMAKE_BUILD_TYPE=Release \
 && cmake --build build --target qucsrflayout -j"$(nproc)"

# ---------------- Stage 2: the TASMEEM image ----------------
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    xfce4 xfce4-terminal dbus-x11 \
    tigervnc-standalone-server novnc websockify \
    ngspice \
    ca-certificates sudo \
 && rm -rf /var/lib/apt/lists/*

# Qucs-S is not in Ubuntu 24.04's repos, so build it from source
# (works on both ARM64 and x86_64). Dependencies come from the Qucs-S README.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential cmake flex bison gperf dos2unix \
    qt6-base-dev qt6-tools-dev qt6-tools-dev-tools libglx-dev linguist-qt6 \
    qt6-l10n-tools libqt6svg6-dev libgl1-mesa-dev libqt6opengl6-dev \
    qt6-qpa-plugins libxcb-cursor0 \
 && rm -rf /var/lib/apt/lists/*

# Build and install Qucs-S 26.1.1 (includes the qucsator_rf submodule).
# This step takes a while the first time (about 10-30 minutes).
RUN git clone --branch 26.1.1 --depth 1 --recurse-submodules --shallow-submodules \
      https://github.com/ra3xdh/qucs_s.git /tmp/qucs_s \
 && cd /tmp/qucs_s && mkdir builddir && cd builddir \
 && cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local \
 && make -j"$(nproc)" \
 && make install \
 && rm -rf /tmp/qucs_s

# vncpasswd lives in its own package on Ubuntu 24.04.
RUN apt-get update && apt-get install -y --no-install-recommends tigervnc-tools \
 && rm -rf /var/lib/apt/lists/*

# ---------------- openEMS (added in step 2) ----------------
# openEMS is not in Ubuntu 24.04's repos either, so build release v0.37.0 from source.
# Dependencies: openEMS docs (VTK 9 on 24.04), Octave for the .m scripts,
# Python for the future TASMEEM GUI, Mesa so the 3D viewer draws without a GPU.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libhdf5-dev libvtk9-dev libvtk9-qt-dev libboost-all-dev libcgal-dev \
    libtinyxml-dev qtbase5-dev libgl1-mesa-dri \
    octave octave-dev \
    python3-dev python3-numpy python3-matplotlib python3-h5py cython3 \
    python3-setuptools python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*

# Build openEMS, CSXCAD and the AppCSXCAD 3D viewer into /opt/openEMS
# (about 15-30 minutes the first time).
RUN git clone --branch v0.37.0 --depth 1 --recurse-submodules --shallow-submodules \
      https://github.com/thliebig/openEMS-Project.git /tmp/openEMS-Project \
 && cd /tmp/openEMS-Project \
 && ./update_openEMS.sh /opt/openEMS --python --python-venv-mode site \
 && rm -rf /tmp/openEMS-Project

# openEMS programs on the PATH, Python bindings ready to import,
# and the Octave functions loaded for every user (no addpath needed).
ENV PATH="/opt/openEMS/venv/bin:/opt/openEMS/bin:${PATH}"
RUN printf "addpath('/opt/openEMS/share/openEMS/matlab');\naddpath('/opt/openEMS/share/CSXCAD/matlab');\n" \
      >> /usr/share/octave/site/m/startup/octaverc

# Compile openEMS's small Octave HDF5 readers now, as root. Otherwise Octave tries to
# compile them on the first far-field calculation and fails (folder is read-only for users).
RUN cd /opt/openEMS/share/openEMS/matlab && octave --no-gui --eval "setup"
# ------------------------------------------------------------

# ---------------- Font for Octave plots (added in step 4) ----------------
# Octave looks for the FreeSans font file when it draws a plot. Ubuntu only installs it as a
# "recommended" package, which --no-install-recommends skips, so without it every plot fails with
# "ft_text_renderer: invalid bounding box, cannot render".
RUN apt-get update && apt-get install -y --no-install-recommends fonts-freefont-otf \
 && rm -rf /var/lib/apt/lists/*
# ------------------------------------------------------------

# ---------------- TASMEEM EM Simulator (added in step 5, from Ash's GUI) ----------------
# A point-and-click antenna app: shapes in pop-up windows, live 3D view, then openEMS runs in
# the background. It drives openEMS from Python, so it does not need Octave (Octave stays in the
# image for the RF Layout scripts). Installed after openEMS so that long build step stays cached.
RUN apt-get update && apt-get install -y --no-install-recommends python3-pyqt5 python3-pyqt5.qtsvg \
 && rm -rf /var/lib/apt/lists/*
# openEMS's installer makes its Python venv without the system packages, so the venv cannot see
# Ubuntu's PyQt5. Link just PyQt5 into the venv.
RUN ln -sfn /usr/lib/python3/dist-packages/PyQt5 \
      "$(/opt/openEMS/venv/bin/python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/PyQt5"
COPY tasmeem-em/ /opt/tasmeem-em/
# Stop the build here with a clear message if any piece the app needs is missing.
RUN python3 -c "import PyQt5.QtWidgets, matplotlib, numpy, h5py; \
from mpl_toolkits.mplot3d.art3d import Poly3DCollection; \
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT; \
from openEMS import openEMS; from CSXCAD import ContinuousStructure; print('TASMEEM EM app: all parts found')"
# ------------------------------------------------------------------------

# ---------------- Qucs-RFlayout (added in step 3) ----------------
# Qucs-S looks for a program called "qucsrflayout" on the PATH (its default setting on Linux),
# so putting it in /usr/local/bin next to qucs-s makes Tools > RF Layout work with no setup.
COPY --from=rflayout-build /src/build/qucsrflayout /usr/local/bin/qucsrflayout
# ------------------------------------------------------------

# Non-root user, home folder doubles as the shared workspace.
# Ubuntu 24.04 already has a user at ID 1000 ("ubuntu"). Replace it so the app user gets ID 1000,
# which matches the first user on most Linux computers (needed to write to the shared work folder).
RUN userdel -r ubuntu 2>/dev/null || true; useradd -m -u 1000 -s /bin/bash tasmeem
USER tasmeem
WORKDIR /home/tasmeem
RUN mkdir -p Desktop QucsWorkspace/user_lib work

# Shared parts library goes here (copy your .lib files into ./library).
COPY --chown=tasmeem:tasmeem library/ /home/tasmeem/QucsWorkspace/user_lib/

# openEMS example: the 2.4 GHz patch antenna checked against CST.
# start.sh copies it into the work folder the first time.
COPY --chown=tasmeem:tasmeem examples/ /home/tasmeem/examples/

# Launcher buttons on the desktop, one per tool.
COPY --chown=tasmeem:tasmeem Qucs-S.desktop openEMS-Octave.desktop TASMEEM-EM.desktop AppCSXCAD.desktop /home/tasmeem/Desktop/
RUN chmod +x /home/tasmeem/Desktop/*.desktop

COPY --chown=tasmeem:tasmeem start.sh /home/tasmeem/start.sh
RUN dos2unix /home/tasmeem/start.sh && chmod +x /home/tasmeem/start.sh

EXPOSE 6080
CMD ["/home/tasmeem/start.sh"]
