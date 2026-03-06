import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Folder configuration for GitHub Environment
# Folder configuration for GitHub Environment
from google_drive_util import upload_file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
DATA_PATH = os.path.join(SCRIPT_DIR, "pkcargo_data.json")
LOG_PATH = os.path.join(SCRIPT_DIR, "scraper_log.txt")
BASE_URL = "https://member.pkcargo.com"

# ─────────────────────────────────────────────
#  Utility
# ─────────────────────────────────────────────

def log(msg):
    try:
        timestamp = datetime.now().strftime('%H:%M:%S')
        full_msg = f"[{timestamp}] {msg}"
        print(full_msg, flush=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(full_msg + "\n")
    except Exception as e:
        print(f"Logging error: {e}")

def load_config():
    # Load from file if exists
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    
    # Overwrite with Environment Variables (Priority for GitHub Actions)
    if os.environ.get("PK_EMAIL"):
        config["email"] = os.environ.get("PK_EMAIL")
    if os.environ.get("PK_PASSWORD"):
        config["password"] = os.environ.get("PK_PASSWORD")
    if os.environ.get("PK_START_PAGE"):
        config["start_page"] = int(os.environ.get("PK_START_PAGE"))
    if os.environ.get("PK_MAX_PAGES"):
        config["max_pages"] = int(os.environ.get("PK_MAX_PAGES"))

    return config

# ─────────────────────────────────────────────
#  Driver Factory
# ─────────────────────────────────────────────

def create_driver(headless=True, block_images=True):
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("--blink-settings=imagesEnabled=false")

    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.media_stream": 2,
        "profile.default_content_setting_values.notifications": 2,
        "disk-cache-size": 4096,
    }
    if block_images:
        prefs["profile.managed_default_content_settings.images"] = 2
    options.add_experimental_option("prefs", prefs)

    service = Service()
    driver = webdriver.Chrome(service=service, options=options)

    driver.set_page_load_timeout(45)
    driver.set_script_timeout(30)
    driver.implicitly_wait(0)

    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setBlockedURLs", {
            "urls": [
                "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg", "*.ico",
                "*google-analytics.com*", "*googletagmanager.com*", "*facebook.com*"
            ]
        })
    except Exception:
        pass

    return driver

# ... (Include other helper functions directly from the previous pkcargo_new.py) ...
# Actually, I should just copy the whole file but with the added environment var support.

def get_text(driver, xpath, clean=None):
    try:
        els = driver.find_elements(By.XPATH, xpath)
        if not els: return None
        text = els[0].text.strip()
        if clean: text = text.replace(clean, "").strip()
        return text or "-"
    except Exception: return None

def get_text_css(driver, selector):
    try:
        els = driver.find_elements(By.CSS_SELECTOR, selector)
        if not els: return None
        return els[0].text.strip() or "-"
    except Exception: return None

class PKCargoScraper:
    def __init__(self, config):
        self.config = config
        self.driver = create_driver(
            headless=config.get("headless", True),
            block_images=config.get("block_images", True),
        )

    def login(self):
        email = self.config.get("email")
        password = self.config.get("password")
        if not email or not password:
            log("[ERR] Email or Password not provided!")
            return False
            
        log(f"[LOGIN] Authenticating as {email}...")
        try:
            self.driver.get(f"{BASE_URL}/login")
            wait = WebDriverWait(self.driver, 20)
            wait.until(EC.presence_of_element_located((By.NAME, "email")))

            self.driver.find_element(By.NAME, "email").send_keys(email)
            self.driver.find_element(By.NAME, "password").send_keys(password)
            self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

            try:
                WebDriverWait(self.driver, 15).until(EC.url_changes(f"{BASE_URL}/login"))
            except Exception: pass

            if "login" not in self.driver.current_url.lower():
                log("[OK] Login successful!")
                return True
            else:
                log(f"[ERR] Login failed. URL: {self.driver.current_url}")
                return False
        except Exception as e:
            log(f"[ERR] Login error: {e}")
            return False

    def get_total_pages(self):
        try:
            self.driver.get(f"{BASE_URL}/shops")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'pagination')]"))
            )
            links = self.driver.find_elements(
                By.XPATH, "//ul[contains(@class, 'pagination')]//li//a"
            )
            pages = [int(a.text.strip()) for a in links if a.text.strip().isdigit()]
            total = max(pages) if pages else 1
            log(f"[DISCOVERY] Found {total} total pages.")
            return total
        except Exception as e:
            log(f"[DISCOVERY] Fallback to 1 page: {e}")
            return 1

    def collect_urls_from_page(self, page_num):
        order_urls = []
        try:
            self.driver.get(f"{BASE_URL}/shops?page={page_num}")
            container_xpath = "/html/body/div[1]/div[2]/div[3]/div[3]/div/div[2]"
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, container_xpath))
            )
            items = self.driver.find_elements(By.XPATH, f"{container_xpath}/div")
            log(f"  [PAGE {page_num}] {len(items)} items found.")
            for item in items:
                try:
                    status_text = "-"
                    status_els = item.find_elements(By.XPATH, "./div/div[1]/div/div[2]")
                    if status_els:
                        status_text = status_els[0].text.strip()
                        # if "ยกเลิก" in status_text: continue # Don't skip, we want to update its status to JSON
                    link_els = item.find_elements(By.XPATH, ".//div/div[2]/div[3]/a")
                    if link_els:
                        url = link_els[0].get_attribute("href")
                        if url: order_urls.append((url, status_text))
                except Exception: pass
        except Exception as e:
            log(f"[ERR] Page {page_num}: {e}")
        return order_urls

    def scrape_detail_page(self, url, list_status="-"):
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//h5[contains(text(), 'ออเดอร์เลขที่')]"))
            )
            try: WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'เรทสั่งซื้อ')]")))
            except Exception: pass
            
            data = {
                "detail_url": url,
                "scraped_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            }
            d = self.driver
            data["order_id"] = get_text(d, "//h5[contains(text(), 'ออเดอร์เลขที่')]", "ออเดอร์เลขที่ :")
            data["date"] = get_text(d, "//div[contains(text(), 'วันที่สร้าง')]", "วันที่สร้าง: ")
            data["status"] = list_status
            data["shipping_type"] = get_text(d, "//div[contains(text(), 'รูปแบบขนส่ง')]", "รูปแบบขนส่ง: ")
            data["order_note"] = get_text(d, "//h6[contains(text(), 'หมายเหตุ')]/following-sibling::div")

            vendors = []
            vendor_blocks = d.find_elements(By.XPATH, "//div[contains(@id, 'vendor-')]")
            for block in vendor_blocks:
                vendor_data = {
                    "vendor_id": block.get_attribute("id"),
                    "products": [],
                    "table_totals": {},
                    "tracking_numbers": [],
                    "_pending": [],
                }
                for row in block.find_elements(By.XPATH, ".//table/tbody/tr"):
                    tds = row.find_elements(By.TAG_NAME, "td")
                    if not tds or len(tds) < 1: continue
                    row_text = row.text.strip()
                    first_cell_text = tds[0].text.strip()

                    # 1. ตรวจสอบว่าเป็นแถว "รวมยอด" หรือไม่ (เช็คเฉพาะคอลัมน์แรก)
                    if first_cell_text == "รวม" and len(tds) >= 4:
                        vendor_data["table_totals"] = {
                            "total_price_cny": tds[1].text.strip() if len(tds) > 1 else "-",
                            "total_qty": tds[2].text.strip() if len(tds) > 2 else "-",
                            "total_ship_cny": tds[3].text.strip() if len(tds) > 3 else "-",
                            "total_all_cny": tds[4].text.strip() if len(tds) > 4 else "-",
                            "total_all_thb": tds[5].text.strip() if len(tds) > 5 else "-",
                        }
                    
                    # 2. ตรวจสอบว่าเป็นแถว "เลขพัสดุ" หรือไม่
                    elif "เลขพัสดุ" in row_text or "tracking" in row_text.lower():
                        for l in row.find_elements(By.TAG_NAME, "a"):
                            href = l.get_attribute("href") or ""
                            if "/forwarders/items/track" in href:
                                vendor_data["_pending"].append({"id": l.text.strip(), "url": href})
                    
                    # 3. แถวอื่นๆ ที่มีคอลัมน์ครบ ให้ถือว่าเป็นสินค้า (แม้ไม่มีลิงก์จีน)
                    elif len(tds) >= 6:
                        links = tds[0].find_elements(By.TAG_NAME, "a")
                        item = {
                            "name": links[0].text.strip() if links else tds[0].text.strip().split('\n')[0],
                            "options": "",
                            "price_cny": tds[1].text.strip() if len(tds) > 1 else "0.00",
                            "qty": tds[2].text.strip() if len(tds) > 2 else "0.00",
                            "ship_cny": tds[3].text.strip() if len(tds) > 3 else "0.00",
                            "total_cny": tds[4].text.strip() if len(tds) > 4 else "0.00",
                            "total_thb": tds[5].text.strip() if len(tds) > 5 else "0.00",
                            "extra_cny": tds[6].text.strip() if len(tds) > 6 else "0.00",
                            "item_note": tds[7].text.strip() if len(tds) > 7 else "-",
                        }
                        
                        # พยายามดึง Option และหมายเหตุภายในคอลัมน์แรก
                        try:
                            opt_divs = tds[0].find_elements(By.XPATH, ".//div/div/div")
                            if opt_divs:
                                item["options"] = opt_divs[0].text.strip()
                                if len(opt_divs) > 1: item["item_internal_note"] = opt_divs[1].text.strip()
                        except: pass
                        
                        vendor_data["products"].append(item)
                vendors.append(vendor_data)

            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            except: pass

            # Improved Summary Extraction (Search by labels)
            summary_labels = {
                "rate": "เรทสั่งซื้อ",
                "extra_pay": "ชำระเงินเพิ่ม",
                "china_shipping": "ค่าขนส่งในจีน",
                "net_cny": "ยอดรวมสุทธิ (หยวน)",
                "net_thb": "ยอดรวมสุทธิ (บาท)",
                "grand_net": "ราคาสุทธิรวมไทย"
            }
            
            summary_data = {}
            for key, label in summary_labels.items():
                val = get_text(d, f"//div[contains(normalize-space(), '{label}')]/following-sibling::div")
                if not val or val == "-":
                    # Try alternate search
                    val = get_text(d, f"//*[contains(text(), '{label}')]/following-sibling::*")
                summary_data[key] = val
            
            data["summary"] = summary_data

            for vendor in vendors:
                results = []
                for t in vendor["_pending"]:
                    log(f"      [TRACKING] {t['id']}")
                    t_data = self.scrape_tracking_page(t["url"])
                    results.append(t_data or {"tracking_id": t["id"]})
                vendor["tracking_numbers"] = results
                del vendor["_pending"]
            data["vendors"] = vendors
            return data
        except Exception as e:
            log(f"    [ERR] Detail {url}: {e}")
            return None

    def scrape_tracking_page(self, url, retries=2):
        for attempt in range(retries + 1):
            try:
                self.driver.get(url)
                WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'card')] | //body")))
                time.sleep(1)
                d = self.driver
                return {
                    "tracking_url": url,
                    "tracking_id": get_text(d, "//h5[contains(text(), 'เลขพัสดุ')]", "เลขพัสดุ:"),
                    "date": get_text(d, "//div[contains(text(), 'วันที่สร้าง')]", "วันที่สร้าง:"),
                    "status": get_text(d, "/html/body/div/div[2]/div[3]/div[3]/div/div/div/div[1]/div[2]/div/div[2]"),
                    "product_description": get_text(d, "//div[contains(text(), 'รายละเอียดสินค้า')]/following-sibling::div"),
                    "note": get_text(d, "//div[contains(text(), 'หมายเหตุ')]/following-sibling::div"),
                    "box_type": get_text(d, "//table//tr/td[2]"),
                    "width": get_text(d, "//table//tr/td[3]"),
                    "length": get_text(d, "//table//tr/td[4]"),
                    "height": get_text(d, "//table//tr/td[5]"),
                    "weight": get_text(d, "//table//tr/td[6]"),
                    "volume": get_text(d, "//table//tr/td[7]"),
                    "shipping_fee": get_text(d, "//table//tr/td[8]"),
                    "crate_fee": get_text(d, "//table//tr/td[9]"),
                    "check_fee": get_text(d, "//table//tr/td[10]"),
                    "other_fee": get_text(d, "//table//tr/td[11]"),
                    "discount": get_text(d, "//table//tr/td[12]"),
                    "total": get_text(d, "//table//tr/td[13]"),
                    "product_type": get_text(d, "//td[contains(text(), 'ประเภทสินค้า')]/following-sibling::td"),
                    "shipped_by": get_text(d, "//td[contains(text(), 'ขนส่งโดย')]/following-sibling::td"),
                    "calculated_by": get_text(d, "//td[contains(text(), 'คิดตาม')]/following-sibling::td"),
                    "shipping_rate": get_text(d, '//*[@id="lb-transport-total"]'),
                    "total_net_thb": get_text(d, '//*[@id="lb-total"]'),
                    # รายละเอียดล็อต (Lot Details)
                    "lot_id": get_text(d, "//td[contains(text(), 'ล็อต:')]/following-sibling::td"),
                    "lot_container_close": get_text(d, "//td[contains(text(), 'ปิดตู้:')]/following-sibling::td"),
                    "lot_status": get_text(d, "//td[contains(text(), 'สถานะ:')]/following-sibling::td"),
                    "lot_departed_china": get_text(d, "//td[contains(text(), 'ออกจากจีน:')]/following-sibling::td"),
                    "lot_arrived_thai": get_text(d, "//td[contains(text(), 'ถึงไทย:')]/following-sibling::td"),
                }
            except Exception as e:
                if attempt < retries:
                    time.sleep(2)
                    continue
                log(f"      [ERR] Tracking {url}: {e}")
                return None

    def close(self):
        try: self.driver.quit()
        except Exception: pass

def worker_scrape_urls(url_batch, config, worker_id):
    results = []
    scraper = PKCargoScraper(config)
    try:
        if not scraper.login(): return results
        for url_info in url_batch:
            url, list_status = url_info
            log(f"  [WORKER-{worker_id}] {url}")
            data = scraper.scrape_detail_page(url, list_status)
            if data: results.append(data)
    except Exception as e: log(f"[WORKER-{worker_id}] Error: {e}")
    finally: scraper.close()
    return results

def save_to_json(new_data):
    if not new_data: return
    old_data = []
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content: old_data = json.loads(content)
        except Exception: pass

    # Merge and update logic
    data_map = {o["order_id"]: o for o in old_data}
    
    for item in new_data:
        order_id = item["order_id"]
        # บันทึกทุกรายการรวมถึงที่ยกเลิกแล้ว
        data_map[order_id] = item

    # นำข้อมูลมาเรียงลำดับตามวันที่
    final_data = list(data_map.values())
    final_data.sort(key=lambda x: x.get('date', ''), reverse=True)

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    log(f"[SUCCESS] Saved {len(final_data)} total orders to {DATA_PATH}.")


import requests

def sync_to_google_drive(new_data):
    """
    ส่งข้อมูลผ่าน HTTP POST ไปยัง Google Apps Script เพื่อให้บันทึกไฟล์ลง Drive
    """
    script_url = os.environ.get("GOOGLE_SCRIPT_URL")
    if not script_url:
        log("[INFO] Skip sync: GOOGLE_SCRIPT_URL not set.")
        return

    log(f"[SYNC] Sending {len(new_data)} orders to Google Drive...")
    try:
        # เตรียมข้อมูลสำหรับการส่ง (เลียนแบบ api_server.py /sync)
        payload = {
            "orders": new_data,
            "products": [], # ไม่ได้ดึงในส่วนนี้
            "parcels": []  # ไม่ได้ดึงในส่วนนี้
        }
        
        response = requests.post(script_url, json=payload, timeout=30)
        if response.status_code == 200:
            log("[OK] Sync to Google Drive successful!")
        else:
            log(f"[ERR] Sync failed. Status: {response.status_code}, Resp: {response.text[:100]}")
    except Exception as e:
        log(f"[ERR] Sync error: {e}")

def main():
    log("=" * 55)
    log(f" PK CARGO SCRAPER (GITHUB + DRIVE SYNC)")
    log("=" * 55)
    config = load_config()
    if not config:
        log("[CRITICAL] config or env vars missing.")
        return

    collector = PKCargoScraper(config)
    all_urls = []
    try:
        if not collector.login(): return
        total_pages = collector.get_total_pages()
        start_p = config.get("start_page", 1)
        max_p = config.get("max_pages", 0)
        end_p = min(start_p + max_p, total_pages + 1) if max_p > 0 else total_pages + 1

        for p in range(start_p, end_p):
            log(f"[COLLECT] Page {p}/{total_pages}")
            urls = collector.collect_urls_from_page(p)
            all_urls.extend(urls)
    finally: collector.close()

    if not all_urls:
        log("[INFO] No URLs found.")
        return

    num_workers = config.get("num_workers", 2)
    chunks = [all_urls[i::num_workers] for i in range(num_workers)]
    all_orders = []
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(worker_scrape_urls, chunk, config, idx): idx for idx, chunk in enumerate(chunks) if chunk}
        for future in as_completed(futures):
            try: all_orders.extend(future.result())
            except Exception: pass

    # 1. บันทึกลงไฟล์บน GitHub
    save_to_json(all_orders)
    
    # 3. อัปโหลดไฟล์ไฟล์ JSON เข้าไปที่ Google Drive โดยตรง
    try:
        # อัปโหลด pkcargo_data.json เข้าไปในโฟลเดอร์ PK
        upload_file(DATA_PATH, "pkcargo_data.json", "PK")
        log("[OK] pkcargo_data.json uploaded to Google Drive folder 'PK'!")
    except Exception as e:
        log(f"[ERR] Failed to upload to GDrive directly: {e}")

    log(" DONE!")

if __name__ == "__main__":
    main()
