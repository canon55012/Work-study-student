"""一般工具：時間。"""
import datetime


def get_current_time() -> str:
    """取得現在的日期時間"""
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S %A")
