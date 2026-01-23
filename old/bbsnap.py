import socket, time, csv
from datetime import datetime

HOST, PORT = "127.0.0.1", 55355

def read_u8(sock, addr):
    cmd = f"READ_CORE_MEMORY {addr:04X} 1"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(4096)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None
    return int(text.split()[-1], 16)

def read_block(sock, addr, nbytes):
    cmd = f"READ_CORE_MEMORY {addr:04X} {nbytes}"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(65535)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None
    parts = text.split()
    hexbytes = parts[-nbytes:]
    try:
        return bytes(int(x, 16) for x in hexbytes)
    except:
        return None

def half_to_inning_side(half):
    # 0=1回表, 1=1回裏, ...
    inning = (half // 2) + 1
    side = "表" if (half % 2) == 0 else "裏"
    return inning, side

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.5)

# 既知のアドレス群
ADDR_BALL = 0xC0C0
ADDR_STR  = 0xC0C2
ADDR_OUT  = 0xC0C3
ADDR_HALF = 0xC0C4

# トリガー（投手操作に戻ると動くやつ）
ADDR_TRIG = 0xC0DD

# “怪しい帯”を保存（まずはあなたの観察帯）
DUMP_BASE = 0xC0B0
DUMP_SIZE = 0x50  # C0B0..C0FF

out_path = "snapshots.csv"

# CSV初期化（ヘッダ）
with open(out_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    header = ["ts", "trig", "balls", "strikes", "outs", "half", "inning", "side"]
    header += [f"{(DUMP_BASE+i):04X}" for i in range(DUMP_SIZE)]
    w.writerow(header)

prev_trig = read_u8(sock, ADDR_TRIG)
print("Logging snapshots on C0DD change... Ctrl+C to stop.")

while True:
    trig = read_u8(sock, ADDR_TRIG)
    if trig is None:
        time.sleep(0.05)
        continue

    if prev_trig is None:
        prev_trig = trig

    # トリガー変化＝“確定状態コミット”の瞬間としてスナップショット
    if trig != prev_trig:
        b  = read_u8(sock, ADDR_BALL)
        s  = read_u8(sock, ADDR_STR)
        o  = read_u8(sock, ADDR_OUT)
        h  = read_u8(sock, ADDR_HALF)
        dump = read_block(sock, DUMP_BASE, DUMP_SIZE)

        if None not in (b, s, o, h) and dump is not None:
            inning, side = half_to_inning_side(h)
            ts = datetime.now().isoformat(timespec="seconds")
            row = [ts, f"{trig:02X}", b, s, o, h, inning, side]
            row += [f"{x:02X}" for x in dump]
            with open(out_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
            print(f"SNAP ts={ts} trig {prev_trig:02X}->{trig:02X}  {inning}回{side}  B/S/O={b}/{s}/{o}")

        prev_trig = trig

    time.sleep(0.02)
