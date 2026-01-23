import socket, time

HOST, PORT = "127.0.0.1", 55355

def read_u8(sock, addr):
    cmd = f"READ_CORE_MEMORY {addr:04X} 1"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(4096)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None
    return int(text.split()[-1], 16)

def half_to_inning_side(half):
    inning = (half // 2) + 1
    side = "表" if (half % 2) == 0 else "裏"
    return inning, side

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.5)

# B/S/O/回
ADDR_BALL = 0xC0C0
ADDR_STR  = 0xC0C2
ADDR_OUT  = 0xC0C3
ADDR_HALF = 0xC0C4

# 投球可能ゲート（あなたの学習結果）
ADDR_MODE = 0xC0D3  # P:00 / F:01

# 塁（0/非0で判定する前提）
ADDR_1B = 0xD262
ADDR_2B = 0xD282
ADDR_3B = 0xD2A2

# 表示状態を保持
state = {
    "inning": None, "side": None,
    "b": None, "s": None, "o": None,
    "on1": False, "on2": False, "on3": False
}

last_print = None
prev_mode = None

print("Gate by C0D3 (P=00, F=01). Prints only when updated. Ctrl+C to stop.")
while True:
    mode = read_u8(sock, ADDR_MODE)
    if mode is None:
        time.sleep(0.02)
        continue

    # ゲート条件：投球可能
    can_pitch = (mode == 0x00)

    # 「F->P になった瞬間」か、「P中に一定間隔で更新」どっちでもいいが、
    # まずは F->P の立ち上がりだけ更新にすると安定する
    rising = (prev_mode is not None and prev_mode != 0x00 and mode == 0x00)

    if rising:
        b = read_u8(sock, ADDR_BALL)
        s = read_u8(sock, ADDR_STR)
        o = read_u8(sock, ADDR_OUT)
        h = read_u8(sock, ADDR_HALF)

        r1 = read_u8(sock, ADDR_1B)
        r2 = read_u8(sock, ADDR_2B)
        r3 = read_u8(sock, ADDR_3B)

        if None not in (b, s, o, h, r1, r2, r3):
            inning, side = half_to_inning_side(h)

            state["inning"] = inning
            state["side"] = side
            state["b"] = b
            state["s"] = s
            state["o"] = o
            state["on1"] = (r1 != 0)
            state["on2"] = (r2 != 0)
            state["on3"] = (r3 != 0)

            bases = f"1B={'●' if state['on1'] else '○'} 2B={'●' if state['on2'] else '○'} 3B={'●' if state['on3'] else '○'}"
            line = f"[UPDATE] {inning}回{side} B/S/O={b}/{s}/{o}  mode={mode:02X}  | {bases}"

            if line != last_print:
                print(line)
                last_print = line

    prev_mode = mode
    time.sleep(0.02)
