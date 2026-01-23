import socket, time
from collections import Counter, defaultdict

HOST, PORT = "127.0.0.1", 55355

BASE = 0xC000
SIZE = 0x0800        # 2KB: C000-C7FF（まずここで十分当たることが多い）
BLOCK = 0x0100       # 256Bずつ読む
CAP_READS = 7        # 1キャプチャ内で7回読んで“最頻値”を取る
CAP_GAP = 0.01

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

def snapshot_mode(sock):
    """同じ領域を複数回読んで、各バイトは最頻値（mode）を採用する。"""
    # counts[i] = Counter of observed byte values at offset i
    counts = [Counter() for _ in range(SIZE)]

    for _ in range(CAP_READS):
        buf = bytearray()
        for a in range(BASE, BASE + SIZE, BLOCK):
            n = min(BLOCK, BASE + SIZE - a)
            buf.extend(read_block(sock, a, n))
        for i, v in enumerate(buf):
            counts[i][v] += 1
        time.sleep(CAP_GAP)

    # choose most common value per byte
    snap = [c.most_common(1)[0][0] if c else 0 for c in counts]
    return snap

def parse_label(s: str):
    s = s.strip().lower()
    if s in ("done", "exit", "quit"):
        return None
    if len(s) != 3 or any(c not in "01" for c in s):
        raise ValueError("mask must be 3 chars like 101 (order: 1B 2B 3B)")
    # 入力順は「1B 2B 3B」
    b1, b2, b3 = int(s[0]), int(s[1]), int(s[2])
    return (b1, b2, b3)

def acc_bit_test(vals, labels, base_idx, bitpos, invert=False):
    ok = 0
    for v, lab in zip(vals, labels):
        pred = (v >> bitpos) & 1
        if invert:
            pred ^= 1
        if pred == lab[base_idx]:
            ok += 1
    return ok / len(vals)

def acc_nonzero(vals, labels, base_idx, mode):
    # mode: "!=0", "!=FF", "==0", "==FF"
    ok = 0
    for v, lab in zip(vals, labels):
        if mode == "!=0":
            pred = 1 if v != 0 else 0
        elif mode == "!=FF":
            pred = 1 if v != 0xFF else 0
        elif mode == "==0":
            pred = 1 if v == 0 else 0
        elif mode == "==FF":
            pred = 1 if v == 0xFF else 0
        else:
            pred = 0
        if pred == lab[base_idx]:
            ok += 1
    return ok / len(vals)

def acc_value_lookup(vals, labels, base_idx):
    """
    値ごとに多数決でラベル(0/1)を割り当てる簡易分類器。
    サンプル少ないと過学習するので“候補出し専用”。
    """
    table = {}
    byval = defaultdict(list)
    for v, lab in zip(vals, labels):
        byval[v].append(lab[base_idx])
    for v, labs in byval.items():
        table[v] = 1 if sum(labs) >= (len(labs)/2) else 0

    ok = 0
    for v, lab in zip(vals, labels):
        pred = table.get(v, 0)
        if pred == lab[base_idx]:
            ok += 1
    return ok / len(vals)

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.7)

    samples = []  # list of (label_tuple, snap:list[int])
    print("Capture loop:")
    print("- Stable moment (pause recommended), input base mask as 3 bits: 1B2B3B (e.g. 101).")
    print("- Type 'done' to analyze.\n")

    while True:
        s = input("bases (1B2B3B) or done> ")
        try:
            lab = parse_label(s)
        except ValueError as e:
            print("  invalid:", e)
            continue
        if lab is None:
            break

        print("  capturing (mode over reads)...")
        snap = snapshot_mode(sock)
        samples.append((lab, snap))
        cnt = Counter(samples[i][0] for i in range(len(samples)))
        print(f"  captured. total={len(samples)} label_counts={dict(cnt)}\n")

    if len(samples) < 6:
        print("Need more samples (>=6 recommended). Try to include at least one '000' and one '111'.")
        return

    labels = [lab for lab, _ in samples]

    # 候補スコア計算
    candidates = []
    for i in range(SIZE):
        addr = BASE + i
        vals = [snap[i] for _, snap in samples]

        # 各塁(1B/2B/3B)それぞれの最良スコアと説明を探す
        per_base = []
        for base_idx, base_name in enumerate(["1B", "2B", "3B"]):
            best = (0.0, "")
            # bit test
            for b in range(8):
                a = acc_bit_test(vals, labels, base_idx, b, invert=False)
                if a > best[0]:
                    best = (a, f"bit{b}=1")
                a = acc_bit_test(vals, labels, base_idx, b, invert=True)
                if a > best[0]:
                    best = (a, f"bit{b}=0(invert)")
            # nonzero family
            for mode in ["!=0", "!=FF", "==0", "==FF"]:
                a = acc_nonzero(vals, labels, base_idx, mode)
                if a > best[0]:
                    best = (a, mode)
            # value lookup (overfit-y)
            a = acc_value_lookup(vals, labels, base_idx)
            if a > best[0]:
                best = (a, "value->label lookup")
            per_base.append((base_name, best[0], best[1]))

        # 総合スコア（平均一致率）
        avg = sum(x[1] for x in per_base) / 3.0

        # 閾値：まずは0.8、出なければ0.75に落として様子を見る
        if avg >= 0.80:
            obs = " ".join(f"{v:02X}" for v in vals)
            detail = " | ".join(f"{bn}:{acc*100:.0f}%({why})" for bn, acc, why in per_base)
            candidates.append((avg, addr, detail, obs))

    candidates.sort(reverse=True, key=lambda x: x[0])

    print("\n=== RESULTS (top 50) ===")
    if not candidates:
        print("No strong candidates >= 80%.")
        print("Next: 1) capture while paused more strictly, 2) collect more samples incl. 000, 3) lower threshold to 75%.")
        return

    for avg, addr, detail, obs in candidates[:50]:
        print(f"{avg*100:5.1f}%  {addr:04X}  {detail}  values={obs}")

if __name__ == "__main__":
    main()
