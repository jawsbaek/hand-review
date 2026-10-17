"""PioSOLVER 스타일 레인지 CSV('핸드,weight' 줄들) -> TexasSolver 레인지 문자열.

CSV 한 줄 = "핸드타입,weight" (예: AA,1 / AKs,0.5). weight 생략 시 1.0.
"""
import csv


def load_range_csv(path):
    with open(path, newline="") as f:
        parts = []
        for row in csv.reader(f):
            if not row or not row[0].strip():
                continue
            hand = row[0].strip()
            weight = float(row[1]) if len(row) > 1 and row[1].strip() else 1.0
            parts.append(hand if weight == 1.0 else f"{hand}:{weight}")
    return ",".join(parts)


def demo():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "r.csv"
        p.write_text("AA,1\nKK,1\nAKs,0.5\n")
        got = load_range_csv(p)
        assert got == "AA,KK,AKs:0.5", got
    print("ok:", got)


if __name__ == "__main__":
    demo()
