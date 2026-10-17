#!/bin/sh
# TexasSolver(CFR 솔버) 바이너리를 .solver/에 내려받는다. macOS 빌드는 x86_64뿐이라
# Apple Silicon에서는 Rosetta(arch -x86_64)로 실행한다 — solver.py가 처리함.
set -e
case "$(uname -s)" in
  Darwin) ASSET=TexasSolver-v0.2.0-MacOs.zip ;;
  Linux) ASSET=TexasSolver-v0.2.0-Linux.zip ;;
  *) echo "지원하지 않는 OS: $(uname -s)" >&2; exit 1 ;;
esac

dest=.solver
rm -rf "$dest"
mkdir -p "$dest"
gh release download v0.2.0 --repo bupticybee/TexasSolver -p "$ASSET" -O "$dest/solver.zip"
unzip -q "$dest/solver.zip" -d "$dest"
inner=$(find "$dest" -mindepth 1 -maxdepth 1 -type d -name 'TexasSolver-*')
mv "$inner"/* "$dest"/
rm -rf "$inner" "$dest/solver.zip" "$dest/__MACOSX" "$dest/TexasSolverGui.app"
chmod +x "$dest/console_solver"
echo "설치 완료: $dest/console_solver"
