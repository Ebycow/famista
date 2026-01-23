import socket, time

HOST, PORT = "127.0.0.1", 55355

def read_u8(sock, addr):
    cmd = f"READ_CORE_MEMORY {addr:04X} 1"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(4096)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None, text
    parts = text.split()
    try:
        v = int(parts[-1], 16)  # 最後の1バイトを拾う想定
        return v, text
    except Exception:
        return None, text

def half_to_inning_side(half):
    # 0=1回表, 1=1回裏, 2=2回表, ...
    if half is None:
        return None
    inning = (half // 2) + 1
    side = "表" if (half % 2) == 0 else "裏"
    return inning, side

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.25)

ADDR_BALL   = 0xC0C0
ADDR_STR    = 0xC0C2
ADDR_OUTS   = 0xC0C3  # ← 見つけたアウト(0-2)
ADDR_HALF   = 0xC0C4  # ← チェンジ回数/ハーフイニング番号っぽいやつ

while True:
    b, rb = read_u8(sock, ADDR_BALL)
    s, rs = read_u8(sock, ADDR_STR)
    o, ro = read_u8(sock, ADDR_OUTS)
    h, rh = read_u8(sock, ADDR_HALF)

    if None in (b, s, o, h):
        print("read failed:",
              f"ball={rb}",
              f"strike={rs}",
              f"outs(C0C3)={ro}",
              f"half(C0C4)={rh}",
              sep="\n  ")
    else:
        inning, side = half_to_inning_side(h)
        # 表示例: "3回表  B=1 S=2 O=1"
        print(f"{inning}回{side}  B={b} S={s} O={o}  (half={h})")

    time.sleep(0.1)
