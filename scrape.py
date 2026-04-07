import asyncio
import os
import json
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

SHEET_REVIEW = "\u30af\u30c1\u30b3\u30df\u6570"
SHEET_BLOG   = "\u30d6\u30ed\u30b0\u6570"


async def fetch_salon(page, url):
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1500)
    try:
        name = await page.title()
        name = name.split("\uff5c")[0].strip()
    except Exception:
        name = "\u4e0d\u660e"
    reviews = 0
    try:
        html = await page.content()
        import re
        m = re.search(r'"reviewCount"\s*:\s*(\d+)', html)
        if m:
            reviews = int(m.group(1))
    except Exception:
        pass
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


def get_or_create_sheet(spreadsheet, sheet_name, salon_names):
    """\u30b7\u30fc\u30c8\u3092\u53d6\u5f97\u307e\u305f\u306f\u65b0\u898f\u4f5c\u6210\u3057\u3001\u5e97\u8217\u540d\u30d8\u30c3\u30c0\u3092\u6574\u5099\u3059\u308b"""
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=50)
        # 1\u884c\u76ee: A1\u306f\u7a7a\u767d\u3001B1\u4ee5\u964d\u306b\u5e97\u8217\u540d
        header = [""] + salon_names
        ws.append_row(header, value_input_option="USER_ENTERED")
        ws.format("A1:A1", {"textFormat": {"bold": True}})
        ws.format(f"B1:{chr(65 + len(salon_names))}1", {
            "backgroundColor": {"red": 0.29, "green": 0.29, "blue": 0.54},
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
        })
    else:
        # \u65e2\u5b58\u30b7\u30fc\u30c8: \u30d8\u30c3\u30c0\u884c\u306e\u5e97\u8217\u540d\u3092\u78ba\u8a8d\u30fb\u8ffd\u52a0
        existing_header = ws.row_values(1)
        for name in salon_names:
            if name not in existing_header:
                existing_header.append(name)
                col = len(existing_header)
                ws.update_cell(1, col, name)
    return ws


def write_to_sheets(results, today):
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not creds_json or not spreadsheet_id:
        raise ValueError("\u74b0\u5883\u5909\u6570\u672a\u8a2d\u5b9a")

    creds_data = json.loads(creds_json)
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)

    salon_names = [r["name"] for r in results]

    # \u30af\u30c1\u30b3\u30df\u6570\u30b7\u30fc\u30c8
    ws_review = get_or_create_sheet(sh, SHEET_REVIEW, salon_names)
    review_row = [today] + [r["reviews"] for r in results]
    ws_review.append_row(review_row, value_input_option="USER_ENTERED")

    # \u30d6\u30ed\u30b0\u6570\u30b7\u30fc\u30c8
    ws_blog = get_or_create_sheet(sh, SHEET_BLOG, salon_names)
    blog_row = [today] + [r["blogs"] for r in results]
    ws_blog.append_row(blog_row, value_input_option="USER_ENTERED")

    print(f"\u2705 \u30b9\u30d7\u30ec\u30c3\u30c9\u30b7\u30fc\u30c8\u306b\u66f8\u304d\u8fbc\u307f\u5b8c\u4e86")


async def main():
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).strftime("%Y/%m/%d")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP", viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        results = []
        for url in URLS:
            try:
                result = await fetch_salon(page, url)
                results.append(result)
                print(f"\u2705 {result['name']}: \u30af\u30c1\u30b3\u30df{result['reviews']}\u4ef6, \u30d6\u30ed\u30b0{result['blogs']}\u4ef6")
            except Exception as e:
                results.append({"name": "\u30a8\u30e9\u30fc", "reviews": "\u30a8\u30e9\u30fc", "blogs": "\u30a8\u30e9\u30fc"})
                print(f"\u274c \u30a8\u30e9\u30fc: {url} / {e}")
            await asyncio.sleep(2)

        await browser.close()

    write_to_sheets(results, today)
    print(f"\u5b8c\u4e86: {today} / {len(results)}\u4ef6")


if __name__ == "__main__":
    asyncio.run(main())
