"""Собрать Windows x64 EXE: python build_exe.py (после requirements-build.txt)."""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Сборка ежедневника в один Windows EXE")
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    parser.add_argument("--build-dir", type=Path, default=root / "build")
    args = parser.parse_args()
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        parser.error("Для этой сборки нужен 64-разрядный Python под Windows.")
    try:
        import PyInstaller.__main__
    except ImportError:
        print("Установите сборщик: python -m pip install -r requirements-build.txt", file=sys.stderr)
        return 1
    dist = args.dist_dir.resolve()
    build = args.build_dir.resolve()
    PyInstaller.__main__.run([
        "--noconfirm", "--onefile", "--windowed", "--noupx",
        "--name", "ListPlanner",
        "--distpath", str(dist),
        "--workpath", str(build / "pyinstaller"),
        "--specpath", str(build),
        # SQL-файл должен оказаться рядом с database.py внутри пакета.
        # __file__ в Repository работает и после распаковки onefile-бандла.
        "--add-data", f"{root / 'planner' / 'schema.sql'}:planner",
        str(root / "main.py"),
    ])
    print(f"Готово: {dist / 'ListPlanner.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
