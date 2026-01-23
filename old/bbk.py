import socket

HOST, PORT = "127.0.0.1", 55355
ADDR = 0xC0DD  # 本命候補

def read_u8(sock, addr):
    cmd = f"READ_CORE_MEMORY {addr:04X} 1"
    sock.sendto(cmd.encode("ascii"), (HOST, PORT))
    data, _ = sock.recvfrom(4096)
    text = data.decode("ascii", errors="replace").strip()
    if " -1" in text:
        return None
    return int(text.split()[-1], 16)

def parse_mask(s):
    s = s.strip().lower()
    if s in ("done", "quit", "exit"):
        return None
    if len(s) != 3 or any(c not in "01" for c in s):
        raise ValueError("use 3 bits: 1B2B3B, e.g. 101")
    return (int(s[0]), int(s[1]), int(s[2]))  # 1B,2B,3B

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.5)

# match[base][bit] = count of (pred == label) across samples
match = [[0]*8 for _ in range(3)]
total = 0

print("Input bases (1B2B3B). Script reads C0DD and learns bit mapping. Type done to stop.")
while True:
    s = input("bases> ")
    try:
        lab = parse_mask(s)
    except ValueError as e:
        print("invalid:", e)
        continue

    if lab is None:
        break

    v = read_u8(sock, ADDR)
    if v is None:
        print("read failed")
        continue

    bits = [(v >> b) & 1 for b in range(8)]  # bit0..bit7
    total += 1
    print(f"C0DD={v:02X} bits={''.join(str(x) for x in bits[::-1])}  label={lab}")

    for base_idx in range(3):
        for b in range(8):
            pred = bits[b]
            if pred == lab[base_idx]:
                match[base_idx][b] += 1

if total == 0:
    print("No samples.")
    raise SystemExit(0)

print("\n=== Bit accuracy by base (higher is better) ===")
for base_idx, name in enumerate(["1B", "2B", "3B"]):
    scores = [(match[base_idx][b]/total, b) for b in range(8)]
    scores.sort(reverse=True)
    top = scores[:3]
    print(f"{name}: " + "  ".join([f"bit{b}={acc*100:.1f}%" for acc, b in top]))

print("\n=== Suggested mapping (best bit per base) ===")
for base_idx, name in enumerate(["1B", "2B", "3B"]):
    best_b = max(range(8), key=lambda b: match[base_idx][b])
    acc = match[base_idx][best_b] / total
    print(f"{name}: bit{best_b}  ({acc*100:.1f}% over {total} samples)")
