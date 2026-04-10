"""
================================================
 London Restaurant Scraper — Google Maps
 Tools: Python + Selenium + Pandas
 Output: london_restaurants.csv
================================================
"""

import time
import random
import re
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
)
import pandas as pd


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
SEARCH_QUERY   = "restaurants in London City"
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE    = os.path.join(BASE_DIR, "london_restaurants.csv")
MAX_RESULTS    = 120
SCROLL_PAUSE   = 2.0
PAGE_LOAD_WAIT = 15       # زودنا الـ wait من 8 لـ 15 ثانية
HEADLESS       = False


# ─────────────────────────────────────────────
#  DRIVER SETUP
# ─────────────────────────────────────────────
def create_driver() -> webdriver.Chrome:
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1400,900")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def random_sleep(min_s=1.0, max_s=2.5):
    time.sleep(random.uniform(min_s, max_s))


def close_popup(driver):
    """
    بيتعامل مع Google consent screen وأي popup تاني.
    بيجرب كل selector — لو مش لاقي حاجة يكمل عادي.
    """
    popup_selectors = [
        # Google consent page
        (By.XPATH,        '//button[.//span[contains(text(),"Accept all")]]'),
        (By.XPATH,        '//button[.//span[contains(text(),"Reject all")]]'),
        (By.XPATH,        '//button[contains(.,"Accept all")]'),
        (By.XPATH,        '//button[contains(.,"Agree")]'),
        (By.XPATH,        '//button[contains(.,"I agree")]'),
        (By.XPATH,        '//button[contains(.,"Accept")]'),
        # Google consent jsnames
        (By.CSS_SELECTOR, 'button[jsname="tQs4af"]'),
        (By.CSS_SELECTOR, 'button[jsname="b3VHJd"]'),
        (By.CSS_SELECTOR, 'form:nth-child(2) button'),
        # Generic
        (By.CSS_SELECTOR, 'button[aria-label="Close"]'),
        (By.CSS_SELECTOR, 'div[aria-label="Close"] button'),
    ]

    for by, sel in popup_selectors:
        try:
            btn = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((by, sel))
            )
            btn.click()
            print("    [popup closed OK]")
            time.sleep(2)
            return
        except (NoSuchElementException, TimeoutException, ElementClickInterceptedException):
            continue

    print("    [no popup — OK]")


def safe_find_text(driver, by, selector, default="N/A") -> str:
    try:
        el = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((by, selector))
        )
        return el.text.strip() or default
    except (TimeoutException, NoSuchElementException):
        return default


# ─────────────────────────────────────────────
#  STEP 1 — Search & collect restaurant links
# ─────────────────────────────────────────────
def collect_restaurant_links(driver) -> list:
    print("[*] Opening Google Maps ...")
    driver.get("https://www.google.com/maps")

    # انتظر تحميل الصفحة الأولية كويس
    time.sleep(5)
    close_popup(driver)
    time.sleep(2)

    # ── بحث ──
    print(f"[*] Searching for: {SEARCH_QUERY}")
    search_box = None

    for selector in ["#searchboxinput", 'input[name="q"]', 'input[aria-label*="Search"]']:
        try:
            search_box = WebDriverWait(driver, PAGE_LOAD_WAIT).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            print(f"    [search box found OK]")
            break
        except TimeoutException:
            continue

    if search_box is None:
        print("[!] Search box NOT found.")
        print(f"    URL:   {driver.current_url}")
        print(f"    Title: {driver.title}")
        return []

    search_box.click()
    time.sleep(1)
    search_box.clear()
    search_box.send_keys(SEARCH_QUERY)
    time.sleep(1)
    search_box.send_keys(Keys.ENTER)
    print("[*] Search submitted — waiting for results ...")
    time.sleep(8)
    # بعد الـ search ممكن يظهر popup تاني
    close_popup(driver)
    time.sleep(3)

    # ── الانتظار لظهور القائمة ──
    # بنجرب أكتر من selector لأن Google Maps بيغير الـ structure
    feed_selectors = [
        'div[role="feed"]',
        'div[aria-label*="Results for"]',
        'div[aria-label*="results"]',
        'div.m6QErb[aria-label]',
    ]
    feed_found = False
    for feed_sel in feed_selectors:
        try:
            WebDriverWait(driver, PAGE_LOAD_WAIT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, feed_sel))
            )
            print(f"[*] Results feed loaded OK ({feed_sel})")
            feed_found = True
            break
        except TimeoutException:
            continue

    if not feed_found:
        print("[!] Results feed not found — saving screenshot for debug ...")
        screenshot_path = os.path.join(BASE_DIR, "debug_screenshot.png")
        driver.save_screenshot(screenshot_path)
        print(f"    Screenshot saved: {screenshot_path}")
        print(f"    URL: {driver.current_url}")
        print(f"    Title: {driver.title}")
        return []

    # ── Scroll لتحميل كل النتائج ──
    print("[*] Scrolling to load more results ...")
    feed = None
    for feed_sel in ['div[role="feed"]', 'div[aria-label*="Results for"]', 'div[aria-label*="results"]', 'div.m6QErb[aria-label]']:
        try:
            feed = driver.find_element(By.CSS_SELECTOR, feed_sel)
            break
        except NoSuchElementException:
            continue
    if feed is None:
        print("[!] Feed element missing.")
        return []

    links = set()
    scroll_attempts = 0
    max_scrolls = 40

    while len(links) < MAX_RESULTS and scroll_attempts < max_scrolls:
        cards = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]')
        for card in cards:
            href = card.get_attribute("href")
            if href and "/maps/place/" in href:
                clean = href.split("?")[0]
                links.add(clean)

        print(f"    -> {len(links)} links so far ...", end="\r")
        driver.execute_script("arguments[0].scrollTop += 800;", feed)
        time.sleep(SCROLL_PAUSE)

        try:
            driver.find_element(
                By.XPATH,
                '//*[contains(text(),"end of the list") or contains(text(),"reached the end")]',
            )
            print("\n[*] Reached end of list.")
            break
        except NoSuchElementException:
            pass

        scroll_attempts += 1

    print(f"\n[+] Total links collected: {len(links)}")
    return list(links)[:MAX_RESULTS]


# ─────────────────────────────────────────────
#  STEP 2 — Extract details from each page
# ─────────────────────────────────────────────
def extract_restaurant_data(driver, url: str) -> dict:
    data = {
        "name":          "N/A",
        "address":       "N/A",
        "phone":         "N/A",
        "website":       "N/A",
        "rating":        "N/A",
        "reviews_count": "N/A",
        "category":      "N/A",
        "opening_hours": "N/A",
        "url":           url,
    }

    try:
        driver.get(url)
        random_sleep(3.0, 4.5)
        close_popup(driver)

        wait = WebDriverWait(driver, PAGE_LOAD_WAIT)

        # Name
        try:
            name_el = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'h1.DUwDvf, h1[class*="fontHeadlineLarge"]')
                )
            )
            data["name"] = name_el.text.strip()
        except TimeoutException:
            pass

        # Rating
        try:
            rating_el = driver.find_element(
                By.CSS_SELECTOR,
                'span.ceNzKf, div.F7nice span[aria-hidden="true"]',
            )
            data["rating"] = rating_el.text.strip()
        except NoSuchElementException:
            pass

        # Reviews count
        try:
            reviews_el = driver.find_element(
                By.CSS_SELECTOR,
                'span[aria-label*="review"], button[aria-label*="review"] span',
            )
            text = reviews_el.get_attribute("aria-label") or reviews_el.text
            match = re.search(r"[\d,]+", text)
            if match:
                data["reviews_count"] = match.group().replace(",", "")
        except NoSuchElementException:
            pass

        # Address / Phone / Website
        info_buttons = driver.find_elements(
            By.CSS_SELECTOR, 'button[data-item-id], a[data-item-id]'
        )
        for btn in info_buttons:
            item_id = btn.get_attribute("data-item-id") or ""
            aria    = btn.get_attribute("aria-label") or ""

            if "address" in item_id.lower() or "address" in aria.lower():
                data["address"] = aria.replace("Address: ", "").strip() or btn.text.strip()
            elif "phone" in item_id.lower() or "phone" in aria.lower():
                data["phone"] = aria.replace("Phone: ", "").strip() or btn.text.strip()
            elif "authority" in item_id.lower() or "website" in item_id.lower():
                href = btn.get_attribute("href") or ""
                data["website"] = href if href.startswith("http") else aria

        # Fallback address
        if data["address"] == "N/A":
            try:
                addr_el = driver.find_element(
                    By.XPATH, '//button[@data-tooltip="Copy address"]'
                )
                data["address"] = addr_el.get_attribute("aria-label") or addr_el.text
            except NoSuchElementException:
                pass

        # ── Category / Type ──
        try:
            cat_el = driver.find_element(
                By.CSS_SELECTOR,
                'button[jsaction*="category"], span.DkEaL, button.DkEaL'
            )
            data["category"] = cat_el.text.strip()
        except NoSuchElementException:
            # fallback: بيدور في الـ aria-label بتاع الـ type button
            try:
                cat_el = driver.find_element(
                    By.XPATH,
                    '//button[@jsaction and contains(@aria-label,"restaurant")]'
                )
                data["category"] = cat_el.get_attribute("aria-label") or cat_el.text
            except NoSuchElementException:
                pass

        # ── Opening Hours ──
        try:
            # بيضغط على زرار الساعات عشان يفتح الـ dropdown
            hours_btn = driver.find_element(
                By.CSS_SELECTOR,
                'div[data-hide-tooltip-on-mobile] [aria-label*="hour"], '
                'button[data-item-id*="hour"], '
                '[aria-label*="Opens"], [aria-label*="Closes"], '
                '[aria-label*="Open now"], [aria-label*="Closed"]'
            )
            aria_hours = hours_btn.get_attribute("aria-label") or ""
            if aria_hours:
                data["opening_hours"] = aria_hours.strip()
            else:
                data["opening_hours"] = hours_btn.text.strip() or "N/A"
        except NoSuchElementException:
            # fallback: بيدور على أي نص فيه "Opens" أو "Closes"
            try:
                hours_el = driver.find_element(
                    By.XPATH,
                    '//*[contains(@aria-label,"Opens") or contains(@aria-label,"Closes") '
                    'or contains(@aria-label,"Open now") or contains(@aria-label,"Closed")]'
                )
                data["opening_hours"] = hours_el.get_attribute("aria-label") or hours_el.text
            except NoSuchElementException:
                pass

    except Exception as e:
        print(f"\n    [!] Error on {url[:60]} -> {e}")

    return data


# ─────────────────────────────────────────────
#  STEP 3 — Save to CSV
# ─────────────────────────────────────────────
def save_to_csv(records: list, filepath: str, final: bool = False):
    if not records:
        print("[!] No data to save.")
        return
    df = pd.DataFrame(records)
    cols = ["name", "category", "address", "phone", "website", "rating", "reviews_count", "opening_hours", "url"]
    df = df[cols]
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f"\n[OK] Saved {len(df)} restaurants -> {filepath}")
    print(df[["name", "rating", "phone"]].head(5).to_string())

    # بعد ما يخلص بالكامل — بيفتح الـ CSV أوتوماتيك
    if final:
        print("\n[*] Opening CSV file ...")
        import subprocess
        subprocess.Popen(["start", "", filepath], shell=True)


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    driver = create_driver()
    results = []

    try:
        links = collect_restaurant_links(driver)
        if not links:
            print("[!] No links found. Exiting.")
            return

        total = len(links)
        print(f"\n[*] Extracting details for {total} restaurants ...\n")

        for i, url in enumerate(links, 1):
            print(f"[{i}/{total}] {url[:70]}...")
            data = extract_restaurant_data(driver, url)
            results.append(data)
            print(
                f"       OK  {data['name'][:38]:38s} | "
                f"Rating: {data['rating']:4s} | "
                f"Phone: {data['phone'][:20]}"
            )

            if i % 10 == 0:
                save_to_csv(results, OUTPUT_FILE)

        save_to_csv(results, OUTPUT_FILE, final=True)

    except KeyboardInterrupt:
        print("\n[!] Interrupted. Saving progress ...")
        save_to_csv(results, OUTPUT_FILE, final=True)

    finally:
        driver.quit()
        print("[*] Browser closed.")


if __name__ == "__main__":
    main()
