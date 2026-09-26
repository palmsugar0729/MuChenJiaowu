"""入口文件，组装各模块并启动应用。"""

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SalaryCounter")

    win = MainWindow()
    win.show()
    win.try_load_autosave()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
