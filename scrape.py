import asyncio
import os
import json
import re
import string
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


def col_letter(n):
    """\u5217\u756a\u53f7(1\u59cb\u307e\u308a)\u3092\u30a2\u30eb\u30d5\u30a1\u30d9\u30c3\u30c8\u306b\u5909\u63db"""
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = string.ascii_uppercase[r] + result
    return result


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
        result = await page.evaluate("""() => {
            const table = document.querySelector('table');
            if (!table) return {};
            const rows = [...table.querySelectorAll('tr')];
            if (rows.length < 3) return {};
            // row[0]: \u6708\u30d8\u30c3\u30c0, row[1]: \u65e5\u4ed8, row[2]: \u30c7\u30fc\u30bf(td)
            const dateRow = rows[1];
            const dateCells = [...dateRow.querySelectorAll('th')];
            const monthTh = rows[0].querySelector('th.monthCell');
            const monthText = monthTh ? monthTh.textContent.trim() : '';
            const monthMatch = monthText.match(/(\\d+)\u5e74(\\d+)\u6708/);
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
            // telColInner\uff08\u304a\u96fb\u8a71\u306b\u3066\u304a\u554f\u3044\u5408\u308f\u305b\u304f\u3060\u3055\u3044\uff09\u3092\u9664\u5916
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
        }""")
        vacancy = result if result else {}
    except Exception as e:
        print(f"vacancy error: {e}")
    return vacancy


def setup_vacancy_sheet(spreadsheet, sheet_name, salon_names):
    """
    \u7a7a\u304d\u67a0\u6570\u30b7\u30fc\u30c8\u306e\u30d8\u30c3\u30c0\u8a2d\u5b9a
    A1=\u7a7a\u767d, B1=\u53d6\u5f97\u65e5, C1=\u5bfe\u8c61\u65e5, D1\u4ee5\u964d=\u5e97\u8217\u540d
    """
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=10000, cols=60)
        ws.update_cell(1, 1, "")          # A1: \u7a7a\u767d
        ws.update_cell(1, 2, "\u53d6\u5f97\u65e5")  # B1: \u53d6\u5f97\u65e5
        ws.update_cell(1, 3, "\u5bfe\u8c61\u65e5")  # C1: \u5bfe\u8c61\u65e5
        for i, name in enumerate(salon_names):
            ws.update_cell(1, i + 4, name)  # D1\u4ee5\u964d: \u5e97\u8217\u540d
        last_col = col_letter(3 + len(salon_names))
        ws.format(f"B1:{last_col}1", {
            "backgroundColor": {"red": 0.29, "green": 0.29, "blue": 0.54},
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
        })
    return ws


def setup_salon_sheet(spreadsheet, sheet_name, salon_names):
    """
    \u30af\u30c1\u30b3\u30df\u6570/\u30d6\u30ed\u30b0\u6570\u30b7\u30fc\u30c8\u306e\u30d8\u30c3\u30c0\u8a2d\u5b9a
    A1=\u7a7a\u767d, B1\u4ee5\u964d=\u5e97\u8217\u540d
    """
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=50)
        ws.update_cell(1, 1, "")
        for i, name in enumerate(salon_names):
            ws.update_cell(1, i + 2, name)
        last_col = col_letter(1 + len(salon_names))
        ws.format(f"B1:{last_col}1", {
            "backgroundColor": {"red": 0.29, "green": 0.29, "blue": 0.54},
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
        })
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

    # \u30af\u30c1\u30b3\u30df\u6570: A1=\u7a7a\u767d, B1\u4ee5\u964d=\u5e97\u8217\u540d, \u30c7\u30fc\u30bf\u884c: A=\u65e5\u4ed8, B\u4ee5\u964d=\u6570\u5024
    ws_review = setup_salon_sheet(sh, SHEET_REVIEW, salon_names)
    ws_review.append_row([today] + [r["reviews"] for r in results], value_input_option="USER_ENTERED")

    # \u30d6\u30ed\u30b0\u6570
    ws_blog = setup_salon_sheet(sh, SHEET_BLOG, salon_names)
    ws_blog.append_row([today] + [r["blogs"] for r in results], value_input_option="USER_ENTERED")

    # \u7a7a\u304d\u67a0\u6570: A1=\u7a7a\u767d, B1=\u53d6\u5f97\u65e5, C1=\u5bfe\u8c61\u65e5, D1\u4ee5\u964d=\u5e97\u8217\u540d
    # \u30c7\u30fc\u30bf\u884c: A=\u7a7a\u767d, B=\u53d6\u5f97\u65e5, C=\u5bfe\u8c61\u65e5, D\u4ee5\u964d=\u6570\u5024
    ws_vac = setup_vacancy_sheet(sh, SHEET_VACANCY, salon_names)
    all_dates = sorted(set(d for vac in vacancy_data.values() for d in vac.keys()))
    rows_to_add = []
    for target_date in all_dates:
        row = ["", today, target_date]  # A=\u7a7a\u767d, B=\u53d6\u5f97\u65e5, C=\u5bfe\u8c61\u65e5
        for r in results:
            vac = vacancy_data.get(r["name"], {})
            row.append(vac.get(target_date, 0))
        rows_to_add.append(row)
    if rows_to_add:
        ws_vac.append_rows(rows_to_add, value_input_option="USER_ENTERED")

    print(f"\u2705 \u5b8c\u4e86: {today}")


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
                print(f"\u2705 {result['name']}: \u30af\u30c1\u30b3\u30df{result['reviews']}\u4ef6 \u30d6\u30ed\u30b0{result['blogs']}\u4ef6")
            except Exception as e:
                results.append({"name": "\u30a8\u30e9\u30fc", "reviews": "\u30a8\u30e9\u30fc", "blogs": "\u30a8\u30e9\u30fc"})
                print(f"\u274c {url}: {e}")
            await asyncio.sleep(2)
        for i, url in enumerate(URLS):
            name = results[i]["name"]
            try:
                vac = await fetch_vacancy(page, url)
                vacancy_data[name] = vac
                print(f"\u2705 \u7a7a\u304d\u67a0 {name}: {len(vac)}\u65e5\u5206 {vac}")
            except Exception as e:
                vacancy_data[name] = {}
                print(f"\u274c \u7a7a\u304d\u67a0\u30a8\u30e9\u30fc {name}: {e}")
            await asyncio.sleep(2)
        await browser.close()
    write_to_sheets(results, vacancy_data, today)
    print(f"\u5b8c\u4e86: {today}")

if __name__ == "__main__":
    asyncio.run(main())
