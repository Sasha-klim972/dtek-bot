import asyncio
import os
import urllib.request
import urllib.parse
from playwright.async_api import async_playwright

BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
CHAT_ID = "917066893"

MY_CITY = "Фастів"
MY_STREET = "Садовий"
MY_HOUSE = "10"
DTEK_URL = "https://www.dtek-krem.com.ua/ua/shutdowns"
SCREENSHOT_FILE = "schedule.png"


def send_telegram_photo(chat_id: str, photo_path: str, caption: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(photo_path, "rb") as photo:
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="parse_mode"\r\n\r\nHTML\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="schedule.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode("utf-8") + photo.read() + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()


async def fetch_schedule_screenshot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 950},
            locale="uk-UA"
        )
        page = await context.new_page()
        await page.goto(DTEK_URL, wait_until="domcontentloaded", timeout=60000)

        try:
            close_btn = page.locator(".modal__close, button.close, .cookie-accept")
            if await close_btn.count() > 0:
                await close_btn.first.click()
        except:
            pass

        # 1. Заповнюємо місто
        try:
            city_input = page.locator("#city")
            if await city_input.count() > 0 and await city_input.is_visible():
                await city_input.fill(MY_CITY)
                await page.wait_for_selector("#cityautocomplete-list div", timeout=7000)
                await page.click("#cityautocomplete-list div >> nth=0")
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Помилка з містом: {e}")

        # 2. Вводимо вулицю
        await page.fill("#street", MY_STREET)
        await page.wait_for_selector("#streetautocomplete-list div", timeout=10000)
        await page.click("#streetautocomplete-list div >> nth=0")
        await asyncio.sleep(1)

        # 3. Вводимо номер будинку
        await page.fill("#house_num", MY_HOUSE)
        await page.wait_for_selector("#house_numautocomplete-list div", timeout=10000)
        await page.click("#house_numautocomplete-list div >> nth=0")
        
        # Чекаємо появи блоку з графіком
        schedule_box = page.locator("#discon-fact")
        await schedule_box.wait_for(state="visible", timeout=15000)
        await schedule_box.screenshot(path=SCREENSHOT_FILE)
        await browser.close()


async def main():
    print("Шукаємо графік для м. Фастів, пров. Садовий, 10...")
    
    try:
        await fetch_schedule_screenshot()
        caption = "🏠 <b>Адреса:</b> м. Фастів, пров. Садовий, 10\n⚡ <i>Графік відключень:</i>"
        send_telegram_photo(CHAT_ID, SCREENSHOT_FILE, caption)
        print("Скріншот успішно надіслано!")
    except Exception as e:
        print(f"Помилка: {e}")
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID,
            "text": f"❌ Не вдалося знайти графік за адресою (м. Фастів, пров. Садовий, 10).\nПомилка: <code>{e}</code>",
            "parse_mode": "HTML"
        }).encode("utf-8")
        urllib.request.urlopen(urllib.request.Request(url, data=data))


if __name__ == "__main__":
    asyncio.run(main())
