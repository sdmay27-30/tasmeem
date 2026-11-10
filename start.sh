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

# First run: copy the Verilog example into the shared work folder too.
if [ ! -d ~/work/verilog_examples ]; then
  cp -r ~/examples/verilog ~/work/verilog_examples
fi

# Verilator GUI: a small web app that listens only inside the container (127.0.0.1:8000).
# The "Verilator GUI" desktop icon opens it in its own window. The one-time token is kept in ~/.vgui_token.
export VGUI_TOKEN="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
echo "$VGUI_TOKEN" > ~/.vgui_token && chmod 600 ~/.vgui_token
/usr/bin/python3 ~/vgui/vgui.py ~/work/verilog_examples >/tmp/vgui.log 2>&1 &

vncserver :1 -geometry 1600x900 -depth 24 -localhost yes
# When the last browser tab disconnects, wait 2 minutes (covers a page reload), then exit.
# This is the container's main process, so the whole container stops and removes itself.
exec websockify --idle-timeout=120 --web /usr/share/novnc 6080 localhost:5901
