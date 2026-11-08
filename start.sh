#!/bin/bash
# Starts the VNC desktop, then the browser bridge on port 6080.
export USER=tasmeem
mkdir -p ~/.vnc
echo "tasmeem" | vncpasswd -f > ~/.vnc/passwd   # simple local password
chmod 600 ~/.vnc/passwd
cat > ~/.vnc/xstartup <<'XS'
#!/bin/sh
unset SESSION_MANAGER DBUS_SESSION_BUS_ADDRESS
exec startxfce4
XS
chmod +x ~/.vnc/xstartup

# First run: copy the openEMS example into the shared work folder
# (so it is saved on your computer and can be edited).
if [ ! -d ~/work/openEMS_examples ]; then
  cp -r ~/examples/openEMS ~/work/openEMS_examples
fi

vncserver :1 -geometry 1600x900 -depth 24 -localhost yes
exec websockify --web /usr/share/novnc 6080 localhost:5901
