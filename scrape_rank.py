import asyncio
import os
import json
import string
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright
import gspread
from google.oauth2.service_account import Credentials

SILK_SALON_IDS = {
    "大阪梅田": "slnH000806594",
    "千葉":     "slnH000806453",
    "松戸":     "slnH000790729",
    "柏":       "slnH000806615",
    "船橋":     "slnH000806584",
    "立川":     "slnH000806618",
    "川崎":     "slnH000806530",
    "秋葉原":   "slnH000806415",
    "赤坂見附": "slnH000806445",
    "浦和":     "slnH000806409",
    "蒲田":     "slnH000806412",
    "池袋東口": "slnH000806602",
    "池袋西口": "slnH000806599",
    "藤沢":     "slnH000580836",
    "渋谷":     "slnH000806420",
}

SEARCH_TARGETS = [
    ("大阪梅田", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre27/city12700000/"),
    ("大阪梅田", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E6%A2%85%E7%94%B0&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("大阪梅田", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=KE&middleAreaCd=KG&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("千葉", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre12/city12100001/"),
    ("千葉", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E5%8D%83%E8%91%89&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("千葉", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AG&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("松戸", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre12/city20700000/"),
    ("松戸", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E6%9D%BE%E6%88%B8&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("松戸", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AG&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("柏", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre12/city21700000/"),
    ("柏", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E6%9F%8F&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("柏", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AG&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("船橋", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre12/city20400000/"),
    ("船橋", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E8%88%B9%E6%A9%8B&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("船橋", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AG&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("立川", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre13/city20200000/"),
    ("立川", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E7%AB%8B%E5%B7%9D&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("立川", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AL&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("川崎", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre14/city14130001/"),
    ("川崎", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E5%B7%9D%E5%B4%8E&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("川崎", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AK&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("秋葉原", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre13/city10600000/"),
    ("秋葉原", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E7%A7%8B%E8%91%89%E5%8E%9F&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("秋葉原", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AC&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("赤坂見附", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre13/city10300000/"),
    ("赤坂見附", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E8%B5%A4%E5%9D%82%E8%A6%8B%E9%99%84&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("赤坂見附", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AE&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("浦和", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre11/city10700000/"),
    ("浦和", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E6%B5%A6%E5%92%8C&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("浦和", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AH&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("蒲田", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre13/city11100000/"),
    ("蒲田", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E8%92%B2%E7%94%B0&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("蒲田", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AI&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("池袋東口", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre13/city11600000/"),
    ("池袋東口", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E6%B1%A0%E8%A2%8B%E6%9D%B1%E5%8F%A3&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("池袋東口", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AB&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("池袋西口", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre13/city11600000/"),
    ("池袋西口", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E6%B1%A0%E8%A2%8B%E8%A5%BF%E5%8F%A3&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("池袋西口", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AB&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("藤沢", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre14/city20500000/"),
    ("藤沢", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E8%97%A4%E6%B2%A2&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("藤沢", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AM&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
    ("渋谷", 1, "https://beauty.hotpepper.jp/genre/kgkw019/pre13/city11300000/"),
    ("渋谷", 2, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9%E3%80%80%E6%B8%8B%E8%B0%B7&searchT=%E6%A4%9C%E7%B4%A2&genreAlias=relax"),
    ("渋谷", 3, "https://beauty.hotpepper.jp/CSP/kr/salonSearch/search/?freeword=%E3%83%94%E3%83%A9%E3%83%86%E3%82%A3%E3%82%B9&serviceAreaCd=SA&middleAreaCd=AD&genreAlias=relax&searchT=%E6%A4%9C%E7%B4%A2"),
]

SHEET_RANK = "(自動更新)掛載順位"
MAX_PAGES = 10


def col_letter(n):
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = string.ascii_uppercase[r] + result
    return result


async def get_rank_from_page(page, base_url, target_salon_id):
    rank_offset = 0
    for pn in range(1, MAX_PAGES + 1):
        if pn == 1:
            url = base_url
        else:
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}pn={pn}"

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)

        salon_links = await page.query_selector_all(".slcHead a[href*='/kr/sln']")
        if not salon_links:
            break

        for i, link in enumerate(salon_links):
            href = await link.get_attribute("href")
            if href and target_salon_id in href:
                return rank_offset + i + 1

        rank_offset += len(salon_links)

        html = await page.content()
        if f"pn={pn + 1}" not in html:
            break

    return None


def setup_rank_sheet(spreadsheet, col_headers):
    try:
        ws = spreadsheet.worksheet(SHEET_RANK)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=SHEET_RANK, rows=5000, cols=len(col_headers) + 2)

    ws.update_cell(1, 1, "")
    ws.update_cell(1, 2, "取得日")
    for i, h in enumerate(col_headers):
        ws.update_cell(1, i + 3, h)

    last_col = col_letter(2 + len(col_headers))
    ws.format(f"B1:{last_col}1", {
        "backgroundColor": {"red": 0.29, "green": 0.29, "blue": 0.54},
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
    })
    return ws


async def main():
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).strftime("%Y/%m/%d")

    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not creds_json or not spreadsheet_id:
        raise ValueError("環境変数未設定")

    creds_data = json.loads(creds_json)
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)

    store_names = list(dict.fromkeys([s[0] for s in SEARCH_TARGETS]))
    col_headers = []
    for store in store_names:
        for p in [1, 2, 3]:
            col_headers.append(f"{store}_P{p}")

    ws = setup_rank_sheet(sh, col_headers)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        rank_row = ["", today]

        for store_name, pattern_no, search_url in SEARCH_TARGETS:
            target_id = SILK_SALON_IDS.get(store_name, "")
            try:
                rank = await get_rank_from_page(page, search_url, target_id)
                rank_row.append(rank if rank is not None else "圈外")
                print(f"✅ {store_name} P{pattern_no}: {rank}位")
            except Exception as e:
                rank_row.append("エラー")
                print(f"❌ {store_name} P{pattern_no}: {e}")
            await asyncio.sleep(2)

        await browser.close()

    ws.append_row(rank_row, value_input_option="USER_ENTERED")
    print(f"✅ 完了: {today}")


if __name__ == "__main__":
    asyncio.run(main())
