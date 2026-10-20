"""Запуск: python main.py [--data-dir PATH] [--demo]."""
from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Лист — ежедневник")
    parser.add_argument("--data-dir", type=Path, help="Папка базы и журнала (по умолчанию папка данных приложения)")
    parser.add_argument("--demo", action="store_true", help="Добавить примеры в пустую базу")
    args = parser.parse_args()
    try:
        from PySide6.QtCore import QLocale, QLockFile, QStandardPaths
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print("python -m pip install -r requirements.txt", file=sys.stderr)
        return 1

    QLocale.setDefault(QLocale("ru_RU"))
    app = QApplication(sys.argv[:1])
    app.setApplicationName("ListPlanner")
    app.setOrganizationName("ListPlanner")
    data_dir = args.data_dir or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(data_dir / "planner.lock"))
        # Активная блокировка проверяется по PID.
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            QMessageBox.information(None, "Лист уже запущен", "Ежедневник с этой базой уже открыт. Проверьте значок в системном трее.")
            return 0
        handler = RotatingFileHandler(data_dir / "planner.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        from planner.database import Repository
        from planner.ui import MainWindow, seed_demo
        repository = Repository(data_dir / "planner.sqlite3")
    except Exception as exc:
        QMessageBox.critical(None, "Ошибка запуска", f"Не удалось открыть ежедневник:\n{exc}")
        return 1

    try:
        if args.demo:
            seed_demo(repository)
        window = MainWindow(repository)
        window.show()
        result = app.exec()
    finally:
        repository.close()
        lock.unlock()
        logging.shutdown()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
