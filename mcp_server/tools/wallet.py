from datetime import datetime, timedelta

from common import wallet, accounts
from mcp_server.tools.vm_lifecycle import wallet_projection


def _depletion_date(days: float) -> str:
    try:
        return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    except (OverflowError, ValueError):
        return "—"


def get_wallet_balance(user_id: str = "default") -> str:
    pt = accounts.plan_type(user_id)
    bal = wallet.balance(user_id)
    proj = wallet_projection(user_id)
    daily, pending, running = proj["daily_burn"], proj["pending"], proj["running"]
    available = bal - pending

    lines = [f"錢包餘額（帳號身分：{pt}）", f"目前餘額：${bal:,.2f}"]
    if pending > 0:
        lines.append(f"運行中未結算（{running} 台）：-${pending:,.2f}")
        lines.append(f"可用餘額：${available:,.2f}")
    if daily > 0:
        lines.append(f"每日燃燒率：${daily:,.2f}/天（實收，依身分折扣後）")
        if available <= 0:
            lines.append("⚠ 可用餘額已用罄或為負，請盡快儲值或關閉不需要的機器（top_up_wallet / stop_vm）")
        else:
            days = available / daily
            lines.append(f"預估可用：約 {days:.1f} 天（約 {_depletion_date(days)} 耗盡）")
            if days < 7:
                lines.append("⚠ 預估 7 天內耗盡，建議及早儲值")
    else:
        lines.append("目前沒有運行中的機器，餘額不會減少（無燃燒）")
    lines.append("提示：可用 top_up_wallet 儲值、list_transactions 查交易明細")
    return "\n".join(lines)


def top_up_wallet(amount: float, user_id: str = "default") -> str:
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return "儲值金額需為數字，例如：儲值 50000 元"
    if amt <= 0:
        return "儲值金額需大於 0"
    bal = wallet.add_funds(user_id, amt, "使用者儲值")
    pt = accounts.plan_type(user_id)
    return (f"✅ 已儲值 ${amt:,.2f}\n"
            f"錢包餘額：${bal:,.2f}（帳號身分：{pt}）\n"
            f"提示：可用 get_wallet_balance 查餘額與預估可用天數")


def list_transactions(limit: int = 20, user_id: str = "default") -> str:
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 20
    n = max(1, min(n, 200))

    pt = accounts.plan_type(user_id)
    txns = wallet.history(user_id)
    if not txns:
        return f"帳號身分：{pt}\n錢包目前沒有任何交易。可用 top_up_wallet 儲值。"

    running_bal, rows = 0.0, []
    for t in txns:
        try:
            running_bal += float(t.get("金額") or 0)
        except (TypeError, ValueError):
            pass
        rows.append((t, running_bal))

    shown = rows[-n:]
    lines = [f"錢包交易明細（帳號身分：{pt}；最近 {len(shown)} 筆，共 {len(rows)} 筆）"]
    for t, bal_after in shown:
        try:
            amt = float(t.get("金額") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        sign = "+" if amt >= 0 else "-"
        note = t.get("說明") or t.get("類型") or ""
        lines.append(f"{t.get('時間', '')} | {t.get('類型', '')} | "
                     f"{sign}${abs(amt):,.2f} | {note} | 餘額 ${bal_after:,.2f}")
    lines.append("─────────────────────────")
    lines.append(f"目前餘額：${wallet.balance(user_id):,.2f}")
    return "\n".join(lines)
