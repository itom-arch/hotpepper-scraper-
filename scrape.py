import asyncio
import os
import json
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright
import gspread
from google.oauth2.service_account import Credentials

URLS = [
    "https://beauty.hotpepper.jp/kr/slnH000806594/",
    "https://beauty.hotpepper.jp/kr/slnH000806453/",
    "https://beauty.hotpepper.jp/kr/slnH000790729/",
    "https://beauty.hotpepper.jp/kr/slnH000806615/",
    "https://beauty.hotpepper.jp/kr/slnH000806584/",
    "https://beauty.hotpepper.jp/kr/slnH000806618/",
    "https://beauty.hotpepper.jp/kr/slnH000806530/",
    "https://beauty.hotpepper.jp/kr/slnH000806415/",
    "https://beauty.hotpepper.jp/kr/slnH000806445/",
    "https://beauty.hotpepper.jp/kr/slnH000806409/",
    "https://beauty.hotpepper.jp/kr/slnH000806412/",
    "https://beauty.hotpepper.jp/kr/slnH000806602/",
    "https://beauty.hotpepper.jp/kr/slnH000806599/",
    "https://beauty.hotpepper.jp/kr/slnH000580836/",
    "https://beauty.hotpepper.jp/kr/slnH000806420/",
    "https://beauty.hotpepper.jp/kr/slnH000569287/",
    "https://beauty.hotpepper.jp/kr/slnH000790732/",
]

SHEET_NAME = "\u30c7\u30fc\u30bf"


async def fetch_salon(page, url):
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1500)

    # \u30b5\u30ed\u30f3\u540d
    try:
        name = await page.title()
        name = name.split("\uff5c")[0].strip()
    except Exception:
        name = "\u4e0d\u660e"

    # \u30af\u30c1\u30b3\u30df\u6570: div.slnHeaderKuchikomiCount \u306e\u300c\uff0831\u4ef6\uff09\u300d\u304b\u3089\u53d6\u5f97
    reviews = 0
    try:
        el = await page.query_selector("div.slnHeaderKuchikomiCount")
        if el:
            text = await el.inner_text()
            m = re.search(r'\d+', text.replace(',', ''))
            if m:
                reviews = int(m.group())
    except Exception:
        pass

    # \u30d6\u30ed\u30b0\u6570: span.numberOfResult \u304b\u3089\u53d6\u5f97
    blogs = 0
    try:
        blog_url = url.rstrip("/") + "/blog/"
        await page.goto(blog_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        el = await page.query_selector("span.numberOfResult")
        if el:
            text = await el.inner_text()
            blogs = int(text.strip().replace(",", ""))
    except Exception:
        pass

    return {"name": name, "reviews": reviews, "blogs": blogs}


def write_to_sheet(rows):
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not creds_json or not spreadsheet_id:
        raise ValueError("\u74b0\u5883\u5909\u6570\u672a\u8a2d\u5b9a")
    creds_data = json.loads(creds_json)
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_NAME, rows=1000, cols=10)
        ws.append_row(["\u65e5\u4ed8", "\u30b5\u30ed\u30f3\u540d", "URL", "\u30af\u30c1\u30b3\u30df\u6570", "\u30d6\u30ed\u30b0\u6570"])
        ws.format("A1:E1", {"backgroundColor": {"red": 0.29, "green": 0.29, "blue": 0.54}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}})
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"\u2705 {len(rows)}\u884c\u66f8\u304d\u8fbc\u307f\u5b8c\u4e86")


async def main():
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).strftime("%Y/%m/%d")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP", viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        rows = []
        for url in URLS:
            try:
                result = await fetch_salon(page, url)
                rows.append([today, result["name"], url, result["reviews"], result["blogs"]])
                print(f"\u2705 {result['name']}: \u30af\u30c1\u30b3\u30df{result['reviews']}\u4ef6, \u30d6\u30ed\u30b0{result['blogs']}\u4ef6")
            except Exception as e:
                rows.append([today, "\u30a8\u30e9\u30fc", url, "\u30a8\u30e9\u30fc", "\u30a8\u30e9\u30fc"])
                print(f"\u274c \u30a8\u30e9\u30fc: {url} / {e}")
            await asyncio.sleep(2)
        await browser.close()
    write_to_sheet(rows)
    print(f"\u5b8c\u4e86: {today} / {len(rows)}\u4ef6")

if __name__ == "__main__":
    asyncio.run(main())
