import socket, time

HOST, PORT = "127.0.0.1", 55355
BASE = 0xC0B0
SIZE = 0x40  # 64 bytesくらい見ておく

def read_block(sock, addr, nbytes):
    cmd = f"READ_CORE_MEMORY {addr:04X} {nbytes}"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(65535)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None, text
    parts = text.split()
    hexbytes = parts[-nbytes:]
    try:
        return bytes(int(x, 16) for x in hexbytes), text
    except:
        return None, text

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.5)

prev = None
print("Watch bytes... Make an OUT and see what changes. Ctrl+C to stop.")
while True:
    blob, raw = read_block(sock, BASE, SIZE)
    if blob is None:
        print("read failed:", raw)
        time.sleep(0.5)
        continue

    if prev is None:
        prev = blob

    # 差分だけ出す
    diffs = []
    for i, (a, b) in enumerate(zip(prev, blob)):
        if a != b:
            diffs.append((BASE + i, a, b))

    if diffs:
        print("CHANGED:")
        for addr, old, new in diffs:
            print(f"  {addr:04X}: {old:02X} -> {new:02X} ({old} -> {new})")
        print("-" * 40)

    prev = blob
    time.sleep(0.1)
