#!/bin/sh
# TexasSolver(CFR 솔버, AGPL-3.0) 바이너리를 .solver/에 내려받는다. macOS 빌드는 x86_64뿐이라
# Apple Silicon에서는 Rosetta(arch -x86_64)로 실행한다 — solver.py가 처리함.
# 받은 zip은 아래 고정 SHA-256과 다르면 설치하지 않는다.
set -e
case "$(uname -s)" in
  Darwin) ASSET=TexasSolver-v0.2.0-MacOs.zip SHA256=5e38b58924d42cb012219a56a9e11b02b6c17fbafd322e374373c22763e7247a ;;
  Linux) ASSET=TexasSolver-v0.2.0-Linux.zip SHA256=4ae5011624378786d436121fb612c807a25ff4878d5bce71b02369a3a311443c ;;
  *) echo "지원하지 않는 OS: $(uname -s)" >&2; exit 1 ;;
esac

cd "$(dirname "$0")/.."
dest=.solver
rm -rf "$dest"
mkdir -p "$dest"
curl -fsSL -o "$dest/solver.zip" "https://github.com/bupticybee/TexasSolver/releases/download/v0.2.0/$ASSET"
echo "$SHA256  $dest/solver.zip" | shasum -a 256 -c -
unzip -q "$dest/solver.zip" -d "$dest"
inner=$(find "$dest" -mindepth 1 -maxdepth 1 -type d -name 'TexasSolver-*')
mv "$inner"/* "$dest"/
rm -rf "$inner" "$dest/solver.zip" "$dest/__MACOSX" "$dest/TexasSolverGui.app"
chmod +x "$dest/console_solver"
echo "설치 완료: $dest/console_solver"
