"""班级费率管理弹窗 — QDialog，支持增删改查。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHBoxLayout,
)


class RateDialog(QDialog):
    def __init__(self, rates: dict[str, float], parent=None):
        super().__init__(parent)
        self.setWindowTitle("班级费率管理")
        self.resize(400, 350)
        self.setMinimumSize(300, 250)

        self._source_rates = rates
        self._result_rates: dict[str, float] | None = None

        self._setup_ui()
        self._populate_table()

    @property
    def rates(self) -> dict[str, float] | None:
        """确定后返回新费率 dict，取消返回 None。"""
        return self._result_rates

    # ── UI 搭建 ──────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["班级类型", "时薪（元/时）"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table)

        # 操作按钮行
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("+ 新增")
        self.del_btn = QPushButton("删除选中")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # 确定/取消
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        root.addWidget(self.button_box)

        self.add_btn.clicked.connect(self._on_add)
        self.del_btn.clicked.connect(self._on_delete)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

    # ── 数据加载 ──────────────────────────────────────

    def _populate_table(self):
        self.table.setRowCount(len(self._source_rates))
        for row, (class_type, rate) in enumerate(self._source_rates.items()):
            type_item = QTableWidgetItem(class_type)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, type_item)

            rate_item = QTableWidgetItem()
            rate_item.setData(Qt.ItemDataRole.DisplayRole, rate)
            rate_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, rate_item)

    # ── 增删操作 ──────────────────────────────────────

    def _on_add(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem("新班级"))
        rate_item = QTableWidgetItem()
        rate_item.setData(Qt.ItemDataRole.DisplayRole, 100)
        self.table.setItem(row, 1, rate_item)
        self.table.editItem(self.table.item(row, 0))

    def _on_delete(self):
        selected = set(idx.row() for idx in self.table.selectedIndexes())
        if not selected:
            return
        if self.table.rowCount() <= len(selected):
            QMessageBox.warning(self, "提示", "至少保留一个班级类型。")
            return
        for row in sorted(selected, reverse=True):
            self.table.removeRow(row)

    # ── 确定/校验 ────────────────────────────────────

    def _on_accept(self):
        new_rates: dict[str, float] = {}
        seen: set[str] = set()

        for row in range(self.table.rowCount()):
            type_item = self.table.item(row, 0)
            rate_item = self.table.item(row, 1)
            if type_item is None or rate_item is None:
                continue

            name = type_item.text().strip()
            if not name:
                QMessageBox.warning(self, "提示", f"第 {row + 1} 行班级类型不能为空。")
                return

            if name in seen:
                QMessageBox.warning(self, "提示", f"班级类型「{name}」重复。")
                return
            seen.add(name)

            try:
                rate = float(rate_item.data(Qt.ItemDataRole.DisplayRole))
            except (TypeError, ValueError):
                QMessageBox.warning(self, "提示", f"第 {row + 1} 行时薪格式不正确。")
                return

            if rate <= 0:
                QMessageBox.warning(self, "提示", f"第 {row + 1} 行时薪必须大于 0。")
                return

            new_rates[name] = rate

        if not new_rates:
            QMessageBox.warning(self, "提示", "至少需要一个班级类型。")
            return

        self._result_rates = new_rates
        self.accept()
