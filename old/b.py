import socket

HOST, PORT = "127.0.0.1", 55355

# まずはB/S/O近辺を広めに見る（必要なら C000..DFFF に拡張）
BASE = 0xC000
SIZE = 0x0200  # 512 bytes（最初は軽め）

def read_block(sock, addr, nbytes):
    cmd = f"READ_CORE_MEMORY {addr:04X} {nbytes}"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(65535)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        raise RuntimeError(text)
    parts = text.split()
    hexbytes = parts[-nbytes:]
    return bytes(int(x, 16) for x in hexbytes)

def bcd_if_possible(v):
    hi, lo = (v >> 4) & 0xF, v & 0xF
    if hi <= 9 and lo <= 9:
        return hi * 10 + lo
    return None

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.5)

prev = None
print("Enterでスナップショット（差分表示） / qで終了")
while True:
    key = input("> ").strip().lower()
    if key == "q":
        break

    cur = read_block(sock, BASE, SIZE)
    if prev is None:
        prev = cur
        print("baseline captured")
        continue

    print("CHANGED:")
    for i, (a, b) in enumerate(zip(prev, cur)):
        if a != b:
            addr = BASE + i
            bcd_a = bcd_if_possible(a)
            bcd_b = bcd_if_possible(b)
            extra = ""
            if bcd_a is not None or bcd_b is not None:
                extra = f"  (BCD {bcd_a}->{bcd_b})"
            print(f"  {addr:04X}: {a:02X}->{b:02X}  ({a}->{b}){extra}")

    prev = cur
