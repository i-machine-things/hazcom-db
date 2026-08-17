"""Entry point for hazcom-db: launches the SDS management desktop app."""

import sys

from PyQt6.QtWidgets import QApplication

from core import db
from ui.main_window import MainWindow


def main() -> int:
    conn = db.connect_and_init()
    app = QApplication(sys.argv)
    window = MainWindow(conn)
    window.show()
    exit_code = app.exec()
    conn.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
