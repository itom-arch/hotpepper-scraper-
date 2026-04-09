import asyncio
import os
import json
import re
import string
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright
import gspread
from google.oauth2.service_account import Credentials

# ===== SILK 17店舗 =====
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

# ===== TADASU 4店舗 =====
URLS_TADASU = [
    "https://beauty.hotpepper.jp/kr/slnH000729540/",
    "https://beauty.hotpepper.jp/kr/slnH000773320/",
    "https://beauty.hotpepper.jp/kr/slnH000795960/",
    "https://beauty.hotpepper.jp/kr/slnH000805329/",
]

SHEET_REVIEW        = "(自動更新)クチコミ数"
SHEET_BLOG          = "(自動更新)ブログ数"
SHEET_VACANCY       = "(自動更新)空き枠数"
SHEET_REVIEW_TADASU = "(自動更新)クチコミ数_TADASU"
SHEET_BLOG_TADASU   = "(自動更新)ブログ数_TADASU"


def col_letter(n):
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
        name = name.split("｜")[0].strip()
    except Exception:
        name = "不明"
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
            const monthMatch = monthText.match(/(\\d+)年(\\d+)月/);
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
        }""")
        vacancy = result if result else {}
    except Exception as e:
        print(f"vacancy error: {e}")
    return vacancy


def setup_salon_sheet(spreadsheet, sheet_name, salon_names):
    """A1=空白, B1以降=店舗名"""
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


def setup_vacancy_sheet(spreadsheet, sheet_name, salon_names):
    """A1=空白, B1=取得日, C1=対象日, D1以降=店舗名"""
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows=10000, cols=60)
        ws.update_cell(1, 1, "")
        ws.update_cell(1, 2, "取得日")
        ws.update_cell(1, 3, "対象日")
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

    # SILK クチコミ数: A1=空白, B1以降=店舗名, データ行: A=日付, B以降=数値
    ws_review = setup_salon_sheet(sh, SHEET_REVIEW, salon_names)
    ws_review.append_row([today] + [r["reviews"] for r in results], value_input_option="USER_ENTERED")

    # SILK ブログ数
    ws_blog = setup_salon_sheet(sh, SHEET_BLOG, salon_names)
    ws_blog.append_row([today] + [r["blogs"] for r in results], value_input_option="USER_ENTERED")

    # SILK 空き枠数: A1=空白, B1=取得日, C1=対象日, D1以降=店舗名
    # データ行: A=空白, B=取得日, C=対象日, D以降=枠数
    ws_vac = setup_vacancy_sheet(sh, SHEET_VACANCY, salon_names)
    all_dates = sorted(set(d for vac in vacancy_data.values() for d in vac.keys()))
    rows_vac = []
    for target_date in all_dates:
        row = ["", today, target_date]
        for r in results:
            row.append(vacancy_data.get(r["name"], {}).get(target_date, 0))
        rows_vac.append(row)
    if rows_vac:
        ws_vac.append_rows(rows_vac, value_input_option="USER_ENTERED")

    # TADASU クチコミ数
    ws_review_t = setup_salon_sheet(sh, SHEET_REVIEW_TADASU, salon_names_tadasu)
    ws_review_t.append_row([today] + [r["reviews"] for r in results_tadasu], value_input_option="USER_ENTERED")

    # TADASU ブログ数
    ws_blog_t = setup_salon_sheet(sh, SHEET_BLOG_TADASU, salon_names_tadasu)
    ws_blog_t.append_row([today] + [r["blogs"] for r in results_tadasu], value_input_option="USER_ENTERED")

    print(f"✅ 書き込み完了: {today}")


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

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="ja-JP", viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        # SILK 17店舗: クチコミ・ブログ取得
        results = []
        for url in URLS:
            try:
                result = await fetch_salon(page, url)
                results.append(result)
                print(f"✅ {result['name']}: クチコミ{result['reviews']}件 ブログ{result['blogs']}件")
            except Exception as e:
                results.append({"name": "エラー", "reviews": "エラー", "blogs": "エラー"})
                print(f"❌ SILK {url}: {e}")
            await asyncio.sleep(2)

        # SILK 17店舗: 空き枠取得
        vacancy_data = {}
        for i, url in enumerate(URLS):
            name = results[i]["name"]
            try:
                vac = await fetch_vacancy(page, url)
                vacancy_data[name] = vac
                print(f"✅ 空き枠 {name}: {len(vac)}日分")
            except Exception as e:
                vacancy_data[name] = {}
                print(f"❌ 空き枠エラー {name}: {e}")
            await asyncio.sleep(2)

        # TADASU 4店舗: クチコミ・ブログ取得
        results_tadasu = []
        for url in URLS_TADASU:
            try:
                result = await fetch_salon(page, url)
                results_tadasu.append(result)
                print(f"✅ TADASU {result['name']}: クチコミ{result['reviews']}件 ブログ{result['blogs']}件")
            except Exception as e:
                results_tadasu.append({"name": "エラー", "reviews": "エラー", "blogs": "エラー"})
                print(f"❌ TADASU {url}: {e}")
            await asyncio.sleep(2)

        await browser.close()

    write_to_sheets(results, vacancy_data, results_tadasu, today, sh)
    print(f"全処理完了: {today}")


if __name__ == "__main__":
    asyncio.run(main())
