import socket, time, os, csv, re
from datetime import datetime

HOST, PORT = "127.0.0.1", 55355

HEXBYTE = re.compile(r"^[0-9A-Fa-f]{2}$")

def read_block(sock, addr, nbytes):
    cmd = f"READ_CORE_MEMORY {addr:04X} {nbytes}"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(65535)
    text = data.decode("ascii", errors="replace").strip()

    if " -1" in text:
        return None, text

    parts = text.split()
    hexbytes = [p for p in parts if HEXBYTE.match(p)]
    if len(hexbytes) < nbytes:
        # 大きく読みすぎるとここに来やすいので、呼び出し側で分割して読む
        return None, text

    # 末尾のnbytes個を採用（先頭側にアドレス等が混ざってもOK）
    hexbytes = hexbytes[-nbytes:]
    return bytes(int(x, 16) for x in hexbytes), text

def read_u8(sock, addr):
    blob, _ = read_block(sock, addr, 1)
    return blob[0] if blob else None

def dump_wram(sock, base, size, chunk=0x0100):
    out = bytearray()
    for a in range(base, base + size, chunk):
        n = min(chunk, base + size - a)
        blob, raw = read_block(sock, a, n)
        if blob is None:
            # チャンクが小さいのに失敗するなら raw を表示して原因確認
            raise RuntimeError(f"read failed at {a:04X} len={n}: {raw}")
        out.extend(blob)
        time.sleep(0.002)  # 少しだけ間を空ける（安定性優先）
    return bytes(out)

def half_to_inning_side(half):
    inning = (half // 2) + 1
    side = "表" if (half % 2) == 0 else "裏"
    return inning, side

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.7)

ADDR_BALL = 0xC0C0
ADDR_STR  = 0xC0C2
ADDR_OUT  = 0xC0C3
ADDR_HALF = 0xC0C4
ADDR_TRIG = 0xC0DD

WRAM_BASE = 0xC000
WRAM_SIZE = 0x2000

os.makedirs("snaps", exist_ok=True)
meta_path = "snaps/meta.csv"
if not os.path.exists(meta_path):
    with open(meta_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["ts","file","trig_hex","inning","side","B","S","O","half","bases_1B2B3B"])

prev = read_u8(sock, ADDR_TRIG)
print("Trigger logging started. Ctrl+C to stop.")

while True:
    trig = read_u8(sock, ADDR_TRIG)
    if trig is None:
        time.sleep(0.02)
        continue
    if prev is None:
        prev = trig

    if trig != prev:
        b = read_u8(sock, ADDR_BALL)
        s = read_u8(sock, ADDR_STR)
        o = read_u8(sock, ADDR_OUT)
        h = read_u8(sock, ADDR_HALF)

        # ここが本体：8KBを分割して読む
        dump = dump_wram(sock, WRAM_BASE, WRAM_SIZE, chunk=0x0100)

        inning, side = half_to_inning_side(h)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        print(f"\nSNAP {inning}回{side} B/S/O={b}/{s}/{o}  (C0DD {prev:02X}->{trig:02X})")
        bases = input("bases (1B2B3B e.g. 101 / blank=skip)> ").strip()
        tag = bases if bases else "---"

        fname = f"snaps/{ts}_trig{trig:02X}_i{inning}{side}_b{b}s{s}o{o}_bases{tag}.bin"
        with open(fname, "wb") as f:
            f.write(dump)

        with open(meta_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([ts,fname,f"{trig:02X}",inning,side,b,s,o,h,bases])

        print(f"saved: {fname}")
        prev = trig

    time.sleep(0.02)
