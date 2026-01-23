import socket, time, os, csv, re, msvcrt
from datetime import datetime
from collections import Counter

HOST, PORT = "127.0.0.1", 55355
HEXBYTE = re.compile(r"^[0-9A-Fa-f]{2}$")

# 投球可能ゲート
ADDR_MODE1 = 0xC0D3  # P:00 / F:01
MODE1_PITCH = 0x00
ADDR_MODE2 = 0xC0CE  # P:14 / F:1A
MODE2_PITCH = 0x14

# WRAM
WRAM_BASE = 0xC000
WRAM_SIZE = 0x2000
CHUNK = 0x0100

CAP_READS = 3   # 重ければ 1 でもOK（まずは収集優先）
CAP_GAP = 0.01

def read_block(sock, addr, nbytes):
    cmd = f"READ_CORE_MEMORY {addr:04X} {nbytes}"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(65535)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None, text
    parts = text.split()
    hb = [p for p in parts if HEXBYTE.match(p)]
    if len(hb) < nbytes:
        return None, text
    hb = hb[-nbytes:]
    return bytes(int(x, 16) for x in hb), text

def read_u8(sock, addr):
    b, _ = read_block(sock, addr, 1)
    return b[0] if b else None

def dump_wram(sock):
    out = bytearray()
    for a in range(WRAM_BASE, WRAM_BASE + WRAM_SIZE, CHUNK):
        n = min(CHUNK, WRAM_BASE + WRAM_SIZE - a)
        blob, raw = read_block(sock, a, n)
        if blob is None:
            raise RuntimeError(f"read failed at {a:04X} len={n}: {raw}")
        out.extend(blob)
        time.sleep(0.001)
    return bytes(out)

def capture_snapshot_mode(sock):
    counters = [Counter() for _ in range(WRAM_SIZE)]
    for _ in range(CAP_READS):
        w = dump_wram(sock)
        for i, v in enumerate(w):
            counters[i][v] += 1
        time.sleep(CAP_GAP)
    return bytes(c.most_common(1)[0][0] for c in counters)

def pitch_ready(sock):
    m1 = read_u8(sock, ADDR_MODE1)
    m2 = read_u8(sock, ADDR_MODE2)
    return (m1 == MODE1_PITCH and m2 == MODE2_PITCH)

os.makedirs("score_snaps", exist_ok=True)
meta_path = "score_snaps/meta.csv"
if not os.path.exists(meta_path):
    with open(meta_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["ts","file","home","away","note"])

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.9)

home = 0
away = 0
pending = False     # “次の投球可能で保存する”フラグ
note = ""

print("Keys:")
print("  h : HOME +1 (run scored)")
print("  a : AWAY +1 (run scored)")
print("  u : undo last change")
print("  s : save snapshot at next pitch-ready (without changing score)")
print("  q : quit\n")

history = []  # (home, away)

prev_ready = False
while True:
    # key input
    if msvcrt.kbhit():
        ch = msvcrt.getwch().lower()
        if ch == "q":
            print("quit.")
            break
        elif ch == "h":
            history.append((home, away))
            home += 1
            pending = True
            note = "HOME+1"
            print(f"[mark] HOME={home} AWAY={away}")
        elif ch == "a":
            history.append((home, away))
            away += 1
            pending = True
            note = "AWAY+1"
            print(f"[mark] HOME={home} AWAY={away}")
        elif ch == "u":
            if history:
                home, away = history.pop()
                pending = True
                note = "UNDO"
                print(f"[undo] HOME={home} AWAY={away}")
        elif ch == "s":
            pending = True
            note = "manual save"
            print(f"[save] scheduled at next pitch-ready: HOME={home} AWAY={away}")

    ready = pitch_ready(sock)

    # 立ち上がり（F->P）だけを“確定の瞬間”として扱う
    if pending and (not prev_ready) and ready:
        print("pitch-ready -> capturing WRAM...")
        snap = capture_snapshot_mode(sock)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"score_snaps/{ts}_H{home}_A{away}.bin"
        with open(fname, "wb") as f:
            f.write(snap)

        with open(meta_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([ts, fname, home, away, note])

        print(f"saved: {fname}")
        pending = False
        note = ""

    prev_ready = ready
    time.sleep(0.02)
