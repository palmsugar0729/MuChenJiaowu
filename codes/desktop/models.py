"""纯数据模型，不依赖任何 UI 或 Excel 库。"""

from dataclasses import dataclass, field
from datetime import date, time

from config import CLASS_RATES, DEFAULT_RATE, WEEKDAY_NAMES


@dataclass
class Record:
    date: date
    start_time: time
    hours: float
    class_type: str
    class_name: str
    note: str = ""

    @property
    def weekday_str(self) -> str:
        return WEEKDAY_NAMES[self.date.weekday()]

    @property
    def rate(self) -> float:
        return CLASS_RATES.get(self.class_type, DEFAULT_RATE)

    @property
    def salary(self) -> float:
        return round(self.hours * self.rate, 2)

    @property
    def group_key(self) -> str:
        """用于颜色分组：按班级名分组，同班级名同色。"""
        return self.class_name


@dataclass
class MonthData:
    teacher_name: str = ""
    records: list[Record] = field(default_factory=list)

    @property
    def total_hours(self) -> float:
        return round(sum(r.hours for r in self.records), 2)

    @property
    def total_salary(self) -> float:
        return round(sum(r.salary for r in self.records), 2)

    def sorted_records(self) -> list[Record]:
        return sorted(self.records, key=lambda r: (r.date, r.start_time))
