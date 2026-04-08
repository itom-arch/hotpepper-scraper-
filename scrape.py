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

SHEET_REVIEW = "(自動更新)クチコミ数"
SHEET_BLOG   = "(自動更新)ブログ数"


async def fetch_salon(page, url):
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1500)
    try:
        name = await page.title()
        name = name.split("｜")[0].strip()
    except Exception:
        name = "不明"
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
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=50)
        ws.update_cell(1, 1, "")
        for i, name in enumerate(salon_names):
            ws.update_cell(1, i + 2, name)
        last_col = chr(65 + len(salon_names))
        ws.format(f"B1:{last_col}1", {
            "backgroundColor": {"red": 0.29, "green": 0.29, "blue": 0.54},
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
        })
        ws.format("A1:A1", {"textFormat": {"bold": True}})
    else:
        existing_header = ws.row_values(1)
        for name in salon_names:
            if name not in existing_header:
                existing_header.append(name)
                ws.update_cell(1, len(existing_header), name)
    return ws


def write_to_sheets(results, today):
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not creds_json or not spreadsheet_id:
        raise ValueError("環境変数未設定")
    creds_data = json.loads(creds_json)
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)
    salon_names = [r["name"] for r in results]
    ws_review = get_or_create_sheet(sh, SHEET_REVIEW, salon_names)
    review_row = [today] + [r["reviews"] for r in results]
    ws_review.append_row(review_row, value_input_option="USER_ENTERED")
    ws_blog = get_or_create_sheet(sh, SHEET_BLOG, salon_names)
    blog_row = [today] + [r["blogs"] for r in results]
    ws_blog.append_row(blog_row, value_input_option="USER_ENTERED")
    print(f"✅ スプレッドシートに書き込み完了")


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
                print(f"✅ {result['name']}: クチコミ{result['reviews']}件, ブログ{result['blogs']}件")
            except Exception as e:
                results.append({"name": "エラー", "reviews": "エラー", "blogs": "エラー"})
                print(f"❌ エラー: {url} / {e}")
            await asyncio.sleep(2)
        await browser.close()
    write_to_sheets(results, today)
    print(f"完了: {today} / {len(results)}件")

if __name__ == "__main__":
    asyncio.run(main())
