import asyncio
import os
import json
import re
import string
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright
import gspread
from google.oauth2.service_account import Credentials

# ===== SILK 17åºè =====
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

# ===== TADASU 4åºè =====
URLS_TADASU = [
    "https://beauty.hotpepper.jp/kr/slnH000729540/",
    "https://beauty.hotpepper.jp/kr/slnH000773320/",
    "https://beauty.hotpepper.jp/kr/slnH000795960/",
    "https://beauty.hotpepper.jp/kr/slnH000805329/",
]

SHEET_REVIEW        = "(èªåæ´æ°)ã¯ãã³ãæ°"
SHEET_BLOG          = "(èªåæ´æ°)ãã­ã°æ°"
SHEET_VACANCY       = "(èªåæ´æ°)ç©ºãæ æ°"
SHEET_REVIEW_TADASU = "(èªåæ´æ°)ã¯ãã³ãæ°_TADASU"
SHEET_BLOG_TADASU   = "(èªåæ´æ°)ãã­ã°æ°_TADASU"


def col_letter(n):
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = string.ascii_uppercase[r] + result
    return result


def append_row_safe(ws, row_data):
    """A列を含む行をずれなく書き込む（append_rowのA列空白時ずれ問題を回避）"""
    all_values = ws.get_all_values()
    next_row = len(all_values) + 1
    end_col = col_letter(len(row_data))
    ws.update(f"A{next_row}:{end_col}{next_row}", [row_data], value_input_option="USER_ENTERED")


def append_rows_safe(ws, rows_data):
    """複数行をA列からずれなく書き込む"""
    if not rows_data:
        return
    all_values = ws.get_all_values()
    next_row = len(all_values) + 1
    end_row = next_row + len(rows_data) - 1
    end_col = col_letter(len(rows_data[0]))
    ws.update(f"A{next_row}:{end_col}{end_row}", rows_data, value_input_option="USER_ENTERED")


async def fetch_salon(page, url):
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1500)
    try:
        name = await page.title()
        name = name.split("ï½")[0].strip()
    except Exception:
        name = "ä¸æ"
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
            const dateRow = rows[1];
            const dateCells = [...dateRow.querySelectorAll('th')];
            const monthTh = rows[0].querySelector('th.monthCell');
            const monthText = monthTh ? monthTh.textContent.trim() : '';
            const monthMatch = monthText.match(/(\\d+)å¹´(\\d+)æ/);
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
            // telColInnerï¼ãé»è©±ã«ã¦ãåãåãããã ããï¼ãé¤å¤
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


def setup_salon_sheet(spreadsheet, sheet_name, salon_names):
    """A1=ç©ºç½, B1ä»¥é=åºèå"""
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=50)
        header = [""] + salon_names
        ws.update("A1", [header], value_input_option="USER_ENTERED")
        last_col = col_letter(1 + len(salon_names))
        ws.format(f"B1:{last_col}1", {
            "backgroundColor": {"red": 0.29, "green": 0.29, "blue": 0.54},
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
        })
    return ws


def setup_vacancy_sheet(spreadsheet, sheet_name, salon_names):
    """A1=ç©ºç½, B1=åå¾æ¥, C1=å¯¾è±¡æ¥, D1ä»¥é=åºèå"""
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=10000, cols=60)
        ws.update_cell(1, 1, "")
        ws.update_cell(1, 2, "åå¾æ¥")
        ws.update_cell(1, 3, "å¯¾è±¡æ¥")
        for i, name in enumerate(salon_names):
            ws.update_cell(1, i + 4, name)
        last_col = col_letter(3 + len(salon_names))
        ws.format(f"B1:{last_col}1", {
            "backgroundColor": {"red": 0.29, "green": 0.29, "blue": 0.54},
            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
        })
    return ws


def write_to_sheets(results, vacancy_data, results_tadasu, today, sh):
    salon_names = [r["name"] for r in results]
    salon_names_tadasu = [r["name"] for r in results_tadasu]

    # SILK ã¯ãã³ãæ°: A1=ç©ºç½, B1ä»¥é=åºèå, ãã¼ã¿è¡: A=æ¥ä», Bä»¥é=æ°å¤
    ws_review = setup_salon_sheet(sh, SHEET_REVIEW, salon_names)
    append_row_safe(ws_review, [today])

    # SILK ãã­ã°æ°
    ws_blog = setup_salon_sheet(sh, SHEET_BLOG, salon_names)
    append_row_safe(ws_blog, [today])

    # SILK ç©ºãæ æ°: A1=ç©ºç½, B1=åå¾æ¥, C1=å¯¾è±¡æ¥, D1ä»¥é=åºèå
    # ãã¼ã¿è¡: A=ç©ºç½, B=åå¾æ¥, C=å¯¾è±¡æ¥, Dä»¥é=æ æ°
    ws_vac = setup_vacancy_sheet(sh, SHEET_VACANCY, salon_names)
    all_dates = sorted(set(d for vac in vacancy_data.values() for d in vac.keys()))
    rows_vac = []
    for target_date in all_dates:
        row = ["", today, target_date]
        for r in results:
            row.append(vacancy_data.get(r["name"], {}).get(target_date, 0))
        rows_vac.append(row)
    if rows_vac:
        append_rows_safe(ws_vac, rows_vac, value_input_option="USER_ENTERED")

    # TADASU ã¯ãã³ãæ°
    ws_review_t = setup_salon_sheet(sh, SHEET_REVIEW_TADASU, salon_names_tadasu)
    append_row_safe(ws_review_t, [today])

    # TADASU ãã­ã°æ°
    ws_blog_t = setup_salon_sheet(sh, SHEET_BLOG_TADASU, salon_names_tadasu)
    append_row_safe(ws_blog_t, [today])

    print(f"â æ¸ãè¾¼ã¿å®äº: {today}")


async def main():
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).strftime("%Y/%m/%d")

    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    if not creds_json or not spreadsheet_id:
        raise ValueError("ç°å¢å¤æ°æªè¨­å®")
    creds_data = json.loads(creds_json)
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(spreadsheet_id)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP", viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        # SILK 17åºè: ã¯ãã³ãã»ãã­ã°åå¾
        results = []
        for url in URLS:
            try:
                result = await fetch_salon(page, url)
                results.append(result)
                print(f"â {result['name']}: ã¯ãã³ã{result['reviews']}ä»¶ ãã­ã°{result['blogs']}ä»¶")
            except Exception as e:
                results.append({"name": "ã¨ã©ã¼", "reviews": "ã¨ã©ã¼", "blogs": "ã¨ã©ã¼"})
                print(f"â SILK {url}: {e}")
            await asyncio.sleep(2)

        # SILK 17åºè: ç©ºãæ åå¾
        vacancy_data = {}
        for i, url in enumerate(URLS):
            name = results[i]["name"]
            try:
                vac = await fetch_vacancy(page, url)
                vacancy_data[name] = vac
                print(f"â ç©ºãæ  {name}: {len(vac)}æ¥å")
            except Exception as e:
                vacancy_data[name] = {}
                print(f"â ç©ºãæ ã¨ã©ã¼ {name}: {e}")
            await asyncio.sleep(2)

        # TADASU 4åºè: ã¯ãã³ãã»ãã­ã°åå¾
        results_tadasu = []
        for url in URLS_TADASU:
            try:
                result = await fetch_salon(page, url)
                results_tadasu.append(result)
                print(f"â TADASU {result['name']}: ã¯ãã³ã{result['reviews']}ä»¶ ãã­ã°{result['blogs']}ä»¶")
            except Exception as e:
                results_tadasu.append({"name": "ã¨ã©ã¼", "reviews": "ã¨ã©ã¼", "blogs": "ã¨ã©ã¼"})
                print(f"â TADASU {url}: {e}")
            await asyncio.sleep(2)

        await browser.close()

    write_to_sheets(results, vacancy_data, results_tadasu, today, sh)
    print(f"å¨å¦çå®äº: {today}")


if __name__ == "__main__":
    asyncio.run(main())
