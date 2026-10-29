"""业务日期的时间口径 —— 「今天」一律按**中国时间（UTC+8）**算。

⚠️ 生产服务器跑的是 UTC。直接 `date.today()` 在中国时间 00:00~08:00 会取到
   **昨天**：那段时间里「今天」的课会被当成未来，老师做不了考勤 —— 而白天又好了，
   这种 bug 只在早上出现，最难查。所以凡是「今天 / 还没到那天」这类业务判断，
   一律走 `today_cn()`。

用固定 `timedelta(hours=8)` 而不是 `ZoneInfo("Asia/Shanghai")`：
  中国不实行夏令时，固定偏移本身就是准的；而且 Windows 开发机没装 tzdata 时
  `zoneinfo` 会直接抛 `ZoneInfoNotFoundError`，没必要为一件确定的事引入依赖。

⚠️ 这只管**业务日期**。`created_at` 那些审计时间戳仍然是 UTC（`models.utcnow`），
   前端用 `formatDateTime()` 转本地时区 —— 两类字段不要混。
"""

from datetime import date as Date
from datetime import datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))


def today_cn() -> Date:
    """中国时间的今天。"""
    return datetime.now(CN_TZ).date()
