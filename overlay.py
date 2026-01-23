import json
import socket
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OVERLAY_PATH = os.path.join(BASE_DIR, "overlay.html")

HOST, PORT = "127.0.0.1", 55355  # RetroArch UDP
HTTP_HOST, HTTP_PORT = "127.0.0.1", 8000  # overlay server

# ====== UI表示用（好きに変えてOK）=====
HOME_NAME = "HOME"
AWAY_NAME = "AWAY"

# ====== 読み取りタイミング ======
COMMIT_DELAY_SEC = 0.20   # ズレるなら 0.25 まで上げる
POLL_SEC = 0.02

# ====== 投球可能ゲート ======
ADDR_MODE1 = 0xC0D3  # P:00 / F:01
ADDR_MODE2 = 0xC0CE  # P:14 / F:1A
MODE1_PITCH = 0x00
MODE2_PITCH = 0x14

# ====== B/S/O/回 ======
ADDR_BALL = 0xC0C0
ADDR_STR  = 0xC0C2
ADDR_OUT  = 0xC0C3
ADDR_HALF = 0xC0C4

# ====== 塁（投球可能タイミングで読む想定：0/非0）=====
ADDR_1B = 0xD262
ADDR_2B = 0xD282
ADDR_3B = 0xD2A2

# ====== スコア本体 ======
ADDR_HOME = 0xD81F
ADDR_AWAY = 0xD83F


def read_u8(sock, addr):
    cmd = f"READ_CORE_MEMORY {addr:04X} 1"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(4096)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None
    return int(text.split()[-1], 16)

def stable_read_u8(sock, addr, n=9, gap=0.01):
    c = Counter()
    for _ in range(n):
        v = read_u8(sock, addr)
        if v is not None:
            c[v] += 1
        time.sleep(gap)
    return c.most_common(1)[0][0] if c else None

def half_to_inning_side(half):
    inning = (half // 2) + 1
    side = "表" if (half % 2) == 0 else "裏"
    return inning, side

def pitch_ready(sock):
    m1 = read_u8(sock, ADDR_MODE1)
    m2 = read_u8(sock, ADDR_MODE2)
    return (m1 == MODE1_PITCH and m2 == MODE2_PITCH), m1, m2

# 共有状態（HTTPから読む）
STATE = {
    "home_name": HOME_NAME,
    "away_name": AWAY_NAME,
    "home": 0,
    "away": 0,
    "inning": 1,
    "side": "表",
    "balls": 0,
    "strikes": 0,
    "outs": 0,
    "on1": False,
    "on2": False,
    "on3": False,
    "updated_at": None,
    "mode1_hex": "--",
    "mode2_hex": "--",
}
STATE_LOCK = threading.Lock()

def updater_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)

    prev_ready = False
    last_home = None
    last_away = None

    while True:
        ready, m1, m2 = pitch_ready(sock)
        with STATE_LOCK:
            STATE["mode1_hex"] = f"{m1:02X}" if m1 is not None else "--"
            STATE["mode2_hex"] = f"{m2:02X}" if m2 is not None else "--"

        # F->P の立ち上がりでだけ確定値を読む
        if (not prev_ready) and ready:
            time.sleep(COMMIT_DELAY_SEC)

            b = read_u8(sock, ADDR_BALL)
            s = read_u8(sock, ADDR_STR)
            o = read_u8(sock, ADDR_OUT)
            h = read_u8(sock, ADDR_HALF)

            r1 = read_u8(sock, ADDR_1B)
            r2 = read_u8(sock, ADDR_2B)
            r3 = read_u8(sock, ADDR_3B)

            home_raw = stable_read_u8(sock, ADDR_HOME)
            away_raw = stable_read_u8(sock, ADDR_AWAY)

            if None not in (b, s, o, h, r1, r2, r3, home_raw, away_raw):
                inning, side = half_to_inning_side(h)
                on1 = (r1 != 0)
                on2 = (r2 != 0)
                on3 = (r3 != 0)

                # スコア単調増加フィルタ（取りこぼし対策）
                if last_home is None or home_raw >= last_home:
                    last_home = home_raw
                if last_away is None or away_raw >= last_away:
                    last_away = away_raw

                with STATE_LOCK:
                    STATE["home_name"] = HOME_NAME
                    STATE["away_name"] = AWAY_NAME
                    STATE["home"] = int(last_home)
                    STATE["away"] = int(last_away)
                    STATE["inning"] = int(inning)
                    STATE["side"] = side
                    STATE["balls"] = int(b)
                    STATE["strikes"] = int(s)
                    STATE["outs"] = int(o)
                    STATE["on1"] = bool(on1)
                    STATE["on2"] = bool(on2)
                    STATE["on3"] = bool(on3)
                    STATE["updated_at"] = time.time()

        prev_ready = ready
        time.sleep(POLL_SEC)

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, content_type, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/state.json"):
            with STATE_LOCK:
                body = json.dumps(STATE, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
            return

        # overlay.html をそのまま配る（同じフォルダに置いてある想定）
        if self.path == "/" or self.path.startswith("/overlay.html"):
            try:
                with open(OVERLAY_PATH, "rb") as f:
                    body = f.read()
                self._send(200, "text/html; charset=utf-8", body)
            except Exception as e:
                self._send(500, "text/plain; charset=utf-8", f"overlay.html read error: {e}\npath={OVERLAY_PATH}".encode("utf-8"))
            return


        self._send(404, "text/plain; charset=utf-8", b"not found")

def main():
    t = threading.Thread(target=updater_loop, daemon=True)
    t.start()
    httpd = HTTPServer((HTTP_HOST, HTTP_PORT), Handler)
    print(f"Overlay server running: http://{HTTP_HOST}:{HTTP_PORT}/overlay.html")
    httpd.serve_forever()

if __name__ == "__main__":
    main()
