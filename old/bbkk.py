import socket

HOST, PORT = "127.0.0.1", 55355
ADDRS = {
    "C0A6": 0xC0A6,
    "C0A5": 0xC0A5,
    "C0DD": 0xC0DD,  # 参考で残す
}

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

# match[name][base][bit] = count(pred==label)
match = {name: [[0]*8 for _ in range(3)] for name in ADDRS.keys()}
total = 0

print("Input bases (1B2B3B). Reads C0A6/C0A5/C0DD and learns bit mapping. Type done to stop.")
while True:
    s = input("bases> ")
    try:
        lab = parse_mask(s)
    except ValueError as e:
        print("invalid:", e)
        continue
    if lab is None:
        break

    vals = {}
    for name, addr in ADDRS.items():
        v = read_u8(sock, addr)
        if v is None:
            print(f"read failed: {name}")
            vals = None
            break
        vals[name] = v
    if vals is None:
        continue

    total += 1
    print(" | ".join([f"{k}={vals[k]:02X}" for k in ADDRS.keys()]) + f"  label={lab}")

    for name, v in vals.items():
        bits = [(v >> b) & 1 for b in range(8)]
        for base_idx in range(3):
            for b in range(8):
                if bits[b] == lab[base_idx]:
                    match[name][base_idx][b] += 1

if total == 0:
    print("No samples.")
    raise SystemExit(0)

print("\n=== Suggested mapping (best bit per base) ===")
for name in ADDRS.keys():
    print(f"\n[{name}]")
    for base_idx, bname in enumerate(["1B","2B","3B"]):
        best_b = max(range(8), key=lambda b: match[name][base_idx][b])
        acc = match[name][base_idx][best_b] / total
        print(f"  {bname}: bit{best_b}  ({acc*100:.1f}% over {total} samples)")
