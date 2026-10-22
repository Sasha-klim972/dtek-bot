import asyncio
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import urllib.request
import urllib.parse
from playwright.async_api import async_playwright

BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
DTEK_URL = os.environ.get("DTEK_URL", "https://www.dtek-kem.com.ua/ua/shutdowns").strip()
MY_GROUP = os.environ.get("MY_GROUP", "GPV1.1").strip()
FORCE_SEND = os.environ.get("FORCE_SEND", "false").lower() == "true"
STATE_FILE = "last_schedule.json"

STATUS_MAP = {
    "yes": "🟢 Світло є",
    "no": "🔴 Відключення",
    "first": "🟠 Немає перші 30 хв",
    "second": "🟠 Немає другі 30 хв",
    "maybe": "🟡 Можливе відключення",
    "mfirst": "🟡 Можливо немає перші 30 хв",
    "msecond": "🟡 Можливо немає другі 30 хв",
}

def get_chat_id(saved_state: dict) -> str:
    if saved_state.get("chat_id"):
        return str(saved_state["chat_id"])
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    for item in reversed(data.get("result", [])):
        msg = item.get("message") or item.get("my_chat_member")
        if msg and "chat" in msg:
            return str(msg["chat"]["id"])
    raise RuntimeError("Бот не бачить вашого чату! Зайдіть у свого бота в Telegram і надішліть йому /start")

def send_telegram_message(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read()

def format_day_schedule(hours_dict: dict) -> str:
    intervals = []
    start_hour = 0
    prev_status = None
    for h in range(1, 25):
        status = hours_dict.get(str(h), "yes")
        if prev_status is None:
            prev_status = status
            start_hour = h - 1
        elif status != prev_status:
            intervals.append((start_hour, h - 1, prev_status))
            start_hour = h - 1
            prev_status = status
    if prev_status is not None:
        intervals.append((start_hour, 24, prev_status))
    lines = []
    for start, end, status in intervals:
        label = STATUS_MAP.get(status, f"⚪ {status}")
        lines.append(f"<code>{start:02d}:00 - {end:02d}:00</code> — {label}")
    return "\n".join(lines)

async def fetch_schedule_from_site() -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            locale="uk-UA",
            timezone_id="Europe/Kyiv"
        )
        page = await context.new_page()
        await page.goto(DTEK_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_function("() => window.DisconSchedule !== undefined", timeout=25000)
        schedule_data = await page.evaluate("() => window.DisconSchedule")
        await browser.close()
        return schedule_data

async def main():
    saved_state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            saved_state = json.load(f)

    chat_id = get_chat_id(saved_state)
    schedule_data = await fetch_schedule_from_site()

    fact = schedule_data.get("fact", {})
    days_data = fact.get("data", {})
    update_time = fact.get("update", "невідомо")

    if not days_data:
        if FORCE_SEND:
            send_telegram_message(chat_id, "ℹ️ На сайті ДТЕК зараз немає опублікованих графіків.")
        return

    first_day_groups = next(iter(days_data.values()))
    if MY_GROUP not in first_day_groups:
        available = ", ".join(sorted(first_day_groups.keys()))
        send_telegram_message(
            chat_id,
            f"⚠️ Групу <b>{MY_GROUP}</b> не знайдено.\n\n"
            f"Доступні варіанти на сайті:\n<code>{available}</code>"
        )
        return

    current_group_schedule = {
        day_ts: days_data[day_ts].get(MY_GROUP, {})
        for day_ts in sorted(days_data.keys(), key=lambda x: int(x))
    }

    if saved_state.get("schedule") == current_group_schedule and not FORCE_SEND:
        print("Графік не змінився.")
        return

    new_state = {"chat_id": chat_id, "schedule": current_group_schedule}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)

    kyiv_tz = ZoneInfo("Europe/Kyiv")
    parts = [
        f"⚡ <b>Графік ДТЕК (Група {MY_GROUP.replace('GPV', '')})</b>\n"
        f"🔄 <i>Оновлено: {update_time}</i>\n"
    ]
    for day_ts, hours_dict in current_group_schedule.items():
        date_str = datetime.fromtimestamp(int(day_ts), tz=kyiv_tz).strftime("%d.%m.%Y")
        parts.append(f"📅 <b>{date_str}</b>\n{format_day_schedule(hours_dict)}\n")

    send_telegram_message(chat_id, "\n".join(parts))

if __name__ == "__main__":
    asyncio.run(main())
