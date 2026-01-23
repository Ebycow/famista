import socket, time
from collections import Counter

HOST, PORT = "127.0.0.1", 55355

# ====== 設定 ======
COMMIT_DELAY_SEC = 0.15   # 投球可能になってからコミット待ち（ズレるなら 0.20〜0.25）
POLL_SEC = 0.02

# 投球可能ゲート（確定）
ADDR_MODE1 = 0xC0D3  # P:00 / F:01
ADDR_MODE2 = 0xC0CE  # P:14 / F:1A
MODE1_PITCH = 0x00
MODE2_PITCH = 0x14

# B/S/O/回
ADDR_BALL = 0xC0C0
ADDR_STR  = 0xC0C2
ADDR_OUT  = 0xC0C3
ADDR_HALF = 0xC0C4

# 塁（投球可能タイミングで読む前提：0/非0）
ADDR_1B = 0xD262
ADDR_2B = 0xD282
ADDR_3B = 0xD2A2

# スコア本体（確定）
ADDR_HOME = 0xD81F
ADDR_AWAY = 0xD83F

# OBSに出したいならファイル出力も可能（Noneならprintだけ）
OUT_FILE = None  # 例: "overlay.txt"

# ====== 共通ユーティリティ ======
def read_u8(sock, addr):
    cmd = f"READ_CORE_MEMORY {addr:04X} 1"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(4096)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None
    return int(text.split()[-1], 16)

def stable_read_u8(sock, addr, n=7, gap=0.01):
    c = Counter()
    for _ in range(n):
        v = read_u8(sock, addr)
        if v is not None:
            c[v] += 1
        time.sleep(gap)
    return c.most_common(1)[0][0] if c else None

def half_to_inning_side(half):
    # 0=1回表, 1=1回裏, 2=2回表...
    inning = (half // 2) + 1
    side = "表" if (half % 2) == 0 else "裏"
    return inning, side

def pitch_ready(sock):
    m1 = read_u8(sock, ADDR_MODE1)
    m2 = read_u8(sock, ADDR_MODE2)
    return (m1 == MODE1_PITCH and m2 == MODE2_PITCH), m1, m2

# ====== メイン ======
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.5)

prev_ready = False

# 画面表示の安定のため保持（スコアは減らない前提でフィルタ）
last_home = None
last_away = None

last_line = None

print("Combined viewer (B/S/O + inning + bases + score) on pitch-ready rising edge. Ctrl+C to stop.")

while True:
    ready, m1, m2 = pitch_ready(sock)

    # F->P の立ち上がりでだけ“確定値”を読む
    if (not prev_ready) and ready:
        time.sleep(COMMIT_DELAY_SEC)

        # B/S/O/回は単発でOK（不安なら stable_read_u8 に変えてもいい）
        b = read_u8(sock, ADDR_BALL)
        s = read_u8(sock, ADDR_STR)
        o = read_u8(sock, ADDR_OUT)
        h = read_u8(sock, ADDR_HALF)

        # 塁は投球可能タイミングでのみ意味がある前提
        r1 = read_u8(sock, ADDR_1B)
        r2 = read_u8(sock, ADDR_2B)
        r3 = read_u8(sock, ADDR_3B)

        # スコアはズレ対策で安定読み
        home_raw = stable_read_u8(sock, ADDR_HOME, n=7, gap=0.01)
        away_raw = stable_read_u8(sock, ADDR_AWAY, n=7, gap=0.01)

        if None not in (b, s, o, h, r1, r2, r3, home_raw, away_raw):
            inning, side = half_to_inning_side(h)

            on1 = (r1 != 0)
            on2 = (r2 != 0)
            on3 = (r3 != 0)

            # スコア単調増加フィルタ（稀な取りこぼし対策）
            if last_home is None or home_raw >= last_home:
                last_home = home_raw
            if last_away is None or away_raw >= last_away:
                last_away = away_raw

            bases = f"1B={'●' if on1 else '○'} 2B={'●' if on2 else '○'} 3B={'●' if on3 else '○'}"
            score = f"HOME={last_home} AWAY={last_away}"

            line = f"{inning}回{side}  B/S/O={b}/{s}/{o}  {bases}  {score}"

            if line != last_line:
                print(line)
                last_line = line

            if OUT_FILE:
                with open(OUT_FILE, "w", encoding="utf-8") as f:
                    f.write(line + "\n")

    prev_ready = ready
    time.sleep(POLL_SEC)
