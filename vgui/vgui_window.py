#!/usr/bin/env python3
"""Opens the Verilator GUI in its own window inside the TASMEEM desktop, like the other tools.
start.sh runs the GUI server in the background and saves its one-time token in ~/.vgui_token."""
import os, sys, time, urllib.request
# Chromium (inside Qt WebEngine) cannot use its own sandbox inside Docker, so turn it off here.
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--no-sandbox --disable-gpu --disable-dev-shm-usage')
rt = '/tmp/runtime-tasmeem'
os.makedirs(rt, mode=0o700, exist_ok=True)
os.environ.setdefault('XDG_RUNTIME_DIR', rt)
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtWebEngineWidgets import QWebEngineView

work = os.path.expanduser('~/work')
try:
    token = open(os.path.expanduser('~/.vgui_token')).read().strip()
except OSError:
    token = ''
url = 'http://127.0.0.1:8000/?t=' + token
app = QApplication(sys.argv)
ready = False
for _ in range(30):                      # the server starts with the desktop; wait for it
    try:
        urllib.request.urlopen(url, timeout=1); ready = True; break
    except Exception:
        time.sleep(1)
if not ready:
    QMessageBox.critical(None, 'Verilator GUI', 'The Verilator GUI server is not running.\nLog: /tmp/vgui.log')
    sys.exit(1)

view = QWebEngineView()
view.setWindowTitle('Verilator GUI')
view.resize(1300, 800)

def on_download(item):                   # Export PNG saves into the shared work folder
    item.setDownloadDirectory(work)
    item.setDownloadFileName(item.suggestedFileName() or 'waveform.png')
    item.accept()
view.page().profile().downloadRequested.connect(on_download)

view.load(QUrl(url))
view.show()
sys.exit(app.exec_())
