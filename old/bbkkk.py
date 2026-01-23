import socket, time
from collections import Counter, defaultdict

HOST, PORT = "127.0.0.1", 55355

BASE = 0xC000
SIZE = 0x2000        # C000-C7FF まず2KB
BLOCK = 0x0100

CAP_READS = 9        # 1キャプチャで9回読む（多いほど安定）
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
    counts = [Counter() for _ in range(SIZE)]
    for _ in range(CAP_READS):
        buf = bytearray()
        for a in range(BASE, BASE + SIZE, BLOCK):
            n = min(BLOCK, BASE + SIZE - a)
            buf.extend(read_block(sock, a, n))
        for i, v in enumerate(buf):
            counts[i][v] += 1
        time.sleep(CAP_GAP)
    return [c.most_common(1)[0][0] for c in counts]

def parse_mask(s):
    s = s.strip().lower()
    if s in ("done", "quit", "exit"):
        return None
    if len(s) != 3 or any(c not in "01" for c in s):
        raise ValueError("use 3 bits: 1B2B3B, e.g. 101")
    # 1B2B3B -> mask(0..7)
    b1, b2, b3 = int(s[0]), int(s[1]), int(s[2])
    return (b1 << 0) | (b2 << 1) | (b3 << 2)

def loocv_accuracy(values, labels):
    """
    1つ抜き交差検証:
    i番目を除いて value->label（多数決）を作り、i番目を予測して当たったか
    """
    n = len(values)
    correct = 0
    for i in range(n):
        table = defaultdict(Counter)
        for j in range(n):
            if j == i: 
                continue
            table[values[j]][labels[j]] += 1

        v = values[i]
        if v in table:
            pred = table[v].most_common(1)[0][0]
        else:
            # 未知値は全体多数決
            pred = Counter(labels[:i] + labels[i+1:]).most_common(1)[0][0]

        if pred == labels[i]:
            correct += 1

    return correct / n

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.7)

    samples = []  # (mask:int, snap:list[int])
    print("Enter bases mask (1B2B3B). Type done to analyze.\n")

    while True:
        s = input("bases> ")
        try:
            m = parse_mask(s)
        except ValueError as e:
            print("invalid:", e)
            continue
        if m is None:
            break

        print("capturing...")
        snap = snapshot_mode(sock)
        samples.append((m, snap))
        print(f"captured. total={len(samples)}\n")

    if len(samples) < 12:
        print("サンプルは12以上あると一気に当たりが出やすい（特に同じ状態を複数回）。")
        # 続行はする

    labels = [m for m, _ in samples]

    candidates = []
    for i in range(SIZE):
        addr = BASE + i
        vals = [snap[i] for _, snap in samples]

        acc = loocv_accuracy(vals, labels)

        # “値が毎回違う”系（タイマ）を弾くために、ユニーク値が多すぎるものを軽く減点
        uniq = len(set(vals))
        score = acc - 0.02 * max(0, uniq - 8)

        if score >= 0.80:
            # 参考表示：ラベルごとの代表値
            bylab = defaultdict(Counter)
            for v, lab in zip(vals, labels):
                bylab[lab][v] += 1
            summary = []
            for lab in sorted(bylab.keys()):
                topv, cnt = bylab[lab].most_common(1)[0]
                summary.append(f"{lab:01X}:{topv:02X}({cnt})")
            candidates.append((score, acc, addr, uniq, " ".join(summary)))

    candidates.sort(reverse=True, key=lambda x: x[0])

    print("\n=== TOP CANDIDATES ===")
    if not candidates:
        print("候補なし。次のどれかが効きます：")
        print("1) SIZEを0x2000（C000-DFFF全部）に増やす")
        print("2) 1状態を2回以上（例: 000を3回、101を3回…）取る")
        print("3) できればポーズ中にキャプチャ")
        return

    for score, acc, addr, uniq, summ in candidates[:30]:
        print(f"score={score:.3f}  loocv={acc*100:5.1f}%  addr={addr:04X}  uniq={uniq:3d}  {summ}")

if __name__ == "__main__":
    main()
