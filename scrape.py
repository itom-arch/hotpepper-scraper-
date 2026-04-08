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

SHEET_REVIEW  = "(\u81ea\u52d5\u66f4\u65b0)\u30af\u30c1\u30b3\u30df\u6570"
SHEET_BLOG    = "(\u81ea\u52d5\u66f4\u65b0)\u30d6\u30ed\u30b0\u6570"
SHEET_VACANCY = "(\u81ea\u52d5\u66f4\u65b0)\u7a7a\u304d\u67a0\u6570"


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


async def fetch_vacancy(page, url):
    store_id_m = re.search(r'slnH(\d+)', url)
    if not store_id_m:
        return {}
    store_id = "H" + store_id_m.group(1)

    reserve_url = f"https://beauty.hotpepper.jp/CSP/kr/reserve/?storeId={store_id}"
    await page.goto(reserve_url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1500)

    coupon_link = await page.query_selector('a[href*="couponId"]')
    if not coupon_link:
        return {}
    coupon_href = await coupon_link.get_attribute("href")
    coupon_m = re.search(r'couponId=(CP\d+)', coupon_href)
    if not coupon_m:
        return {}
    coupon_id = coupon_m.group(1)

    cal_url = f"https://beauty.hotpepper.jp/CSP/kr/reserve/afterCoupon?storeId={store_id}&couponId={coupon_id}&add=0"
    await page.goto(cal_url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    vacancy = {}
    try:
        result = await page.evaluate("""
        () => {
            const table = document.querySelector('table');
            if (!table) return {};
            const rows = [...table.querySelectorAll('tr')];
            if (rows.length < 3) return {};

            const dateRow = rows[1];
            const dateCells = [...dateRow.querySelectorAll('th')];

            const monthTh = rows[0].querySelector('th.monthCell');
            const monthText = monthTh ? monthTh.textContent.trim() : '';
            const monthMatch = monthText.match(/(\\d+)\\u5e74(\\d+)\\u6708/);
            const year = monthMatch ? parseInt(monthMatch[1]) : new Date().getFullYear();
            const month = monthMatch ? parseInt(monthMatch[2]) : new Date().getMonth() + 1;

            const dates = dateCells.map(th => {
                const m = th.textContent.trim().match(/(\\d+)/);
                return m ? parseInt(m[1]) : null;
            }).filter(d => d !== null);

            const numDates = dates.length;
            if (numDates === 0) return {};

            const dataRow = rows[2];
            const allTds = [...dataRow.querySelectorAll('td')];

            // telColInner（お電話にてお問い合わせください）を除外
            const realTds = allTds.filter(td => !td.classList.contains('telColInner'));
            const comaPerDay = Math.round(realTds.length / numDates);

            const result = {};
            dates.forEach((day, i) => {
                const start = i * comaPerDay;
                const end = start + comaPerDay;
                const dayTds = realTds.slice(start, end);
                const openCount = dayTds.filter(td => td.classList.contains('open')).length;
                const mm = String(month).padStart(2, '0');
                const dd = String(day).padStart(2, '0');
                result[year + '/' + mm + '/' + dd] = openCount;
            });
            return result;
        }
        """)
        vacancy = result if result else {}
    except Exception as e:
        print(f"vacancy error: {e}")

    return vacancy


def get_or_create_sheet(spreadsheet, sheet_name, header_row):
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=10000, cols=50)
        ws.update_cell(1, 1, "")
        for i, h in enumerate(header_row):
            ws.update_cell(1, i + 2, h)
        last_col = chr(65 + len(header_row))
        ws.format(f"B1:{last_col}1", {
            "backgroundColor": {"red": 0.29, "green": 0.29, "blue": 0.54},
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
        })
    else:
        existing = ws.row_values(1)
        for h in header_row:
            if h not in existing:
                existing.append(h)
                ws.update_cell(1, len(existing), h)
    return ws


def write_to_sheets(results, vacancy_data, today):
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

    ws_review = get_or_create_sheet(sh, SHEET_REVIEW, salon_names)
    ws_review.append_row([today] + [r["reviews"] for r in results], value_input_option="USER_ENTERED")

    ws_blog = get_or_create_sheet(sh, SHEET_BLOG, salon_names)
    ws_blog.append_row([today] + [r["blogs"] for r in results], value_input_option="USER_ENTERED")

    ws_vac = get_or_create_sheet(sh, SHEET_VACANCY, ["\u5bfe\u8c61\u65e5"] + salon_names)
    all_dates = sorted(set(
        d for vac in vacancy_data.values() for d in vac.keys()
    ))
    rows_to_add = []
    for target_date in all_dates:
        row = [today, target_date]
        for r in results:
            vac = vacancy_data.get(r["name"], {})
            row.append(vac.get(target_date, 0))
        rows_to_add.append(row)
    if rows_to_add:
        ws_vac.append_rows(rows_to_add, value_input_option="USER_ENTERED")

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
        vacancy_data = {}

        for url in URLS:
            try:
                result = await fetch_salon(page, url)
                results.append(result)
                print(f"\u2705 {result['name']}: \u30af\u30c1\u30b3\u30df{result['reviews']}\u4ef6, \u30d6\u30ed\u30b0{result['blogs']}\u4ef6")
            except Exception as e:
                results.append({"name": "\u30a8\u30e9\u30fc", "reviews": "\u30a8\u30e9\u30fc", "blogs": "\u30a8\u30e9\u30fc"})
                print(f"\u274c \u30a8\u30e9\u30fc: {url} / {e}")
            await asyncio.sleep(2)

        for i, url in enumerate(URLS):
            name = results[i]["name"]
            try:
                vac = await fetch_vacancy(page, url)
                vacancy_data[name] = vac
                print(f"\u2705 \u7a7a\u304d\u67a0 {name}: {len(vac)}\u65e5\u5206")
            except Exception as e:
                vacancy_data[name] = {}
                print(f"\u274c \u7a7a\u304d\u67a0\u30a8\u30e9\u30fc {name}: {e}")
            await asyncio.sleep(2)

        await browser.close()

    write_to_sheets(results, vacancy_data, today)
    print(f"\u5b8c\u4e86: {today}")


if __name__ == "__main__":
    asyncio.run(main())
