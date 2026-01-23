import socket, time
from collections import Counter

HOST, PORT = "127.0.0.1", 55355

def read_u8(sock, addr):
    cmd = f"READ_CORE_MEMORY {addr:04X} 1"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(4096)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None
    return int(text.split()[-1], 16)

# 投球可能ゲート
ADDR_MODE1 = 0xC0D3  # P:00 / F:01
ADDR_MODE2 = 0xC0CE  # P:14 / F:1A

# スコア本体
ADDR_HOME = 0xD81F
ADDR_AWAY = 0xD83F

def pitch_ready(sock):
    m1 = read_u8(sock, ADDR_MODE1)
    m2 = read_u8(sock, ADDR_MODE2)
    return (m1 == 0x00 and m2 == 0x14)

def stable_read(sock, addr, n=7, gap=0.01):
    c = Counter()
    for _ in range(n):
        v = read_u8(sock, addr)
        if v is not None:
            c[v] += 1
        time.sleep(gap)
    return c.most_common(1)[0][0] if c else None

# ★ここが抜けてた
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.5)

prev_ready = False
last_home = None
last_away = None

print("Print score on pitch-ready rising edge. Ctrl+C to stop.")
while True:
    ready = pitch_ready(sock)

    if (not prev_ready) and ready:
        time.sleep(0.15)  # コミット待ち（必要なら0.20〜0.25）

        h = stable_read(sock, ADDR_HOME)
        a = stable_read(sock, ADDR_AWAY)

        if h is not None and a is not None:
            if last_home is None or h >= last_home:
                last_home = h
            if last_away is None or a >= last_away:
                last_away = a

            print(f"SCORE  HOME={last_home}  AWAY={last_away}   (raw H={h} A={a})")

    prev_ready = ready
    time.sleep(0.02)
