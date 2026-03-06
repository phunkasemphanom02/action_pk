import datetime
import time
import os
import sys
import shutil
import glob
import calendar
from google_drive_util import upload_and_convert_to_gsheet
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

# ปรับการแสดงผลภาษาไทย
sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIGURATION ---
ZORT_EMAIL = os.environ.get("ZORT_EMAIL")
ZORT_PASS = os.environ.get("ZORT_PASS")
CHROME_DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

if not os.path.exists(CHROME_DOWNLOAD_DIR):
    os.makedirs(CHROME_DOWNLOAD_DIR)

TARGET_DRIVE_FOLDER = ""

def get_last_three_months_be():
    """คืนค่า 3 เดือนย้อนหลัง (รวมเดือนปัจจุบัน) ในรูปแบบ BE"""
    now = datetime.datetime.now()
    months = []
    for i in range(1, 4):  # เดือนที่แล้ว, 2 เดือนที่แล้ว, 3 เดือนที่แล้ว (ไม่รวมเดือนปัจจุบัน)
        target_month = now.month - i
        target_year = now.year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        
        year_be = target_year + 543
        _, days = calendar.monthrange(target_year, target_month)
        
        months.append({
            "month": target_month,
            "year_be": year_be,
            "year_ad": target_year,
            "days": days
        })
    return months


def run_export():
    print("🚀 กำลังเริ่มระบบ Export ยอดขายจาก Zort...")
    
    months_to_export = get_last_three_months_be()
    formatted_months = [f"{m['month']}/{m['year_be']}" for m in months_to_export]
    print(f"📅 เดือนที่จะ Export: {formatted_months}")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": CHROME_DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })
    
    driver = webdriver.Chrome(options=chrome_options)
    wait = WebDriverWait(driver, 30)

    try:
        # ===== 1. Login =====
        print("🔑 กำลังล็อกอิน...")
        driver.get("https://secure.zortout.com/Home/LogOn")
        wait.until(EC.presence_of_element_located((By.NAME, "usernametxt"))).send_keys(ZORT_EMAIL)
        driver.find_element(By.NAME, "passwordtxt").send_keys(ZORT_PASS)
        driver.find_element(By.CSS_SELECTOR, "button.button-primary").click()
        
        wait.until(EC.url_contains("/Dashboard/Initial"))
        print("✅ ล็อกอินสำเร็จ")

        for month_info in months_to_export:
            m = month_info['month']
            y_be = month_info['year_be']
            y_ad = month_info['year_ad']
            
            print(f"\n📊 --- กำลังดำเนินการเดือน {m}/{y_be} (CE: {m}/{y_ad}) ---")

            # ===== 2. ไปหน้ายอดขาย (Sales Report) =====
            print("🌐 กำลังไปหน้ายอดขาย...")
            driver.get("https://secure.zortout.com/Dashboard/SalesReport?")
            time.sleep(5)
            
            # ปิด Widget/Chat ที่อาจบัง
            try:
                driver.execute_script("""
                    document.querySelectorAll('.task-manager-close, #task-manager-close, #close-chat, .fad.fa-times-circle, .close').forEach(el => {
                        try { el.click(); } catch(e) {}
                    });
                """)
            except: pass

            # ===== 3. คลิกปุ่ม "Export สรุปยอดขายรายเดือน ไฟล์ Excel" =====
            try:
                print("🖱️ กำลังหาปุ่ม 'Export สรุปยอดขายรายเดือน ไฟล์ Excel'...")
                
                # คลิกปุ่ม "Export สรุปยอดขายรายเดือน ไฟล์ Excel" (ปุ่มที่ 2 จาก 3 ปุ่ม)
                export_btn = driver.execute_script("""
                    var btns = document.querySelectorAll('button, a, .btn');
                    for(var i=0; i<btns.length; i++){
                        var txt = btns[i].textContent.trim();
                        if(txt.indexOf('สรุปยอดขายรายเดือน') !== -1){
                            return btns[i];
                        }
                    }
                    return null;
                """)
                
                if export_btn:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", export_btn)
                    time.sleep(1)
                    try:
                        export_btn.click()
                    except:
                        driver.execute_script("arguments[0].click();", export_btn)
                    print("✅ คลิกปุ่ม Export สำเร็จ")
                else:
                    print("⚠️ ไม่พบปุ่ม Export... ลองใช้ JS function")
                    # Fallback: ลองเรียก JS ของ Zort โดยตรง
                    driver.execute_script("if(typeof openMonthlySalesExcel === 'function') openMonthlySalesExcel();")
                    
            except Exception as e:
                print(f"⚠️ ไม่สามารถคลิกปุ่ม Export: {e}")
                continue

            # ===== 4. จัดการ Modal Export: เลือกเดือน =====
            try:
                print("⏳ รอหน้าต่าง Export...")
                time.sleep(3)
                
                # หา Modal ที่กำลังแสดงอยู่
                visible_modal = driver.execute_script("""
                    var modals = document.querySelectorAll('.modal');
                    for(var i=0; i<modals.length; i++){
                        var style = window.getComputedStyle(modals[i]);
                        if(style.display !== 'none' && style.visibility !== 'hidden'){
                            return modals[i];
                        }
                    }
                    return null;
                """)
                
                if not visible_modal:
                    time.sleep(3)
                    visible_modal = driver.execute_script("""
                        var modals = document.querySelectorAll('.modal');
                        for(var i=0; i<modals.length; i++){
                            var style = window.getComputedStyle(modals[i]);
                            if(style.display !== 'none' && style.visibility !== 'hidden'){
                                return modals[i];
                            }
                        }
                        return null;
                    """)
                
                if visible_modal:
                    modal_id = visible_modal.get_attribute("id")
                    print(f"✅ พบ Modal: id='{modal_id}'")
                else:
                    print("⚠️ ไม่พบ Modal...")

                # ดูข้อมูล input fields ใน modal
                date_inputs = driver.execute_script("""
                    var modals = document.querySelectorAll('.modal');
                    var visibleModal = null;
                    for(var i=0; i<modals.length; i++){
                        var style = window.getComputedStyle(modals[i]);
                        if(style.display !== 'none' && style.visibility !== 'hidden'){
                            visibleModal = modals[i];
                            break;
                        }
                    }
                    if(!visibleModal) return [];
                    var inputs = visibleModal.querySelectorAll('input[type="text"], input:not([type])');
                    var result = [];
                    for(var j=0; j<inputs.length; j++){
                        result.push({
                            id: inputs[j].id,
                            name: inputs[j].name,
                            value: inputs[j].value,
                            readonly: inputs[j].readOnly,
                            placeholder: inputs[j].placeholder || ''
                        });
                    }
                    return result;
                """)
                
                print(f"🔍 พบ input fields ใน Modal: {len(date_inputs)} ช่อง")
                for di in date_inputs:
                    print(f"   id='{di['id']}' name='{di['name']}' value='{di['value']}' readonly={di['readonly']} placeholder='{di['placeholder']}'")

                # กรอกช่องเดือนใน Modal (รายเดือน ใช้แค่ frommonth / tomonth)
                # สำหรับ Zort บัญชีไทย ต้องส่งเป็นปี พ.ศ. (y_be) เพราะ UI รอรับ พ.ศ. 
                # ถ้าส่ง ค.ศ. (2024) ระบบจะเข้าใจว่าเป็น พ.ศ. 2024 และลบออก 543 จนกลายเป็น ค.ศ. 1481
                from_month_val = f"{m:02d}/{y_be}"
                to_month_val = f"{m:02d}/{y_be}"
                print(f"📅 กรอกเดือน: {from_month_val} ถึง {to_month_val} (พ.ศ.)")
                
                def fill_input_by_id(input_id, value):
                    """กรอกค่าลงใน input ตาม ID โดยตรง"""
                    for attempt in range(5):
                        success = driver.execute_script("""
                            var el = document.getElementById(arguments[0]);
                            if(!el) return 'NOT_FOUND';
                            el.removeAttribute('readonly');
                            el.value = '';
                            el.value = arguments[1];
                            el.dispatchEvent(new Event('focus', {bubbles: true}));
                            el.dispatchEvent(new Event('input', {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            el.dispatchEvent(new Event('blur', {bubbles: true}));
                            try {
                                if(window.jQuery || window.$) {
                                    $(el).val(arguments[1]).trigger('change').trigger('blur');
                                    var dp = $(el).closest('.form_date, .input-group.date, .input-group');
                                    if(dp.length && dp.data('datetimepicker')) {
                                        dp.data('datetimepicker').update();
                                    }
                                }
                            } catch(e) {}
                            return el.value;
                        """, input_id, value)
                        
                        time.sleep(1)
                        if success == value:
                            print(f"✅ {input_id} = {success}")
                            return True
                        elif success == 'NOT_FOUND':
                            print(f"⚠️ ไม่พบ input id='{input_id}'")
                            return False
                        else:
                            print(f"   ลองใหม่ รอบที่ {attempt+2}... (ได้ '{success}')")
                    return False
                
                fill_input_by_id('productModalfrommonth', from_month_val)
                fill_input_by_id('productModaltomonth', to_month_val)
                
                # ===== 5. คลิกปุ่ม ตกลง =====
                confirm_btn = driver.execute_script("""
                    var modals = document.querySelectorAll('.modal');
                    for(var i=0; i<modals.length; i++){
                        var style = window.getComputedStyle(modals[i]);
                        if(style.display !== 'none' && style.visibility !== 'hidden'){
                            var btns = modals[i].querySelectorAll('button');
                            for(var j=0; j<btns.length; j++){
                                if(btns[j].textContent.trim().indexOf('ตกลง') !== -1){
                                    return btns[j];
                                }
                            }
                        }
                    }
                    return null;
                """)

                # เคลียร์ไฟล์เก่า (Sales Report ใช้ชื่อ monthlySales_...)
                for f in glob.glob(os.path.join(CHROME_DOWNLOAD_DIR, 'monthlySales_*.xlsx')):
                    try: os.remove(f)
                    except: pass
                initial_files = set(glob.glob(os.path.join(CHROME_DOWNLOAD_DIR, 'monthlySales_*.xlsx')))

                print("💾 คลิกปุ่มตกลง และรอการดาวน์โหลด...")
                if confirm_btn:
                    driver.execute_script("arguments[0].click();", confirm_btn)
                else:
                    print("⚠️ ไม่พบปุ่มตกลง ลองค้นหาด้วย XPath...")
                    fb = driver.find_element(By.XPATH, "//button[contains(., 'ตกลง')]")
                    driver.execute_script("arguments[0].click();", fb)
                
                # ===== 6. รอดาวน์โหลดไฟล์ =====
                downloaded_file = None
                
                # ===== 6. รอไฟล์ดาวน์โหลด (Zort ใช้ async export) =====
                # วิธี: รอดูไฟล์ monthlySales_*.xlsx ใหม่ใน Downloads สูงสุด 3 นาที
                downloaded_file = None
                print("⏳ รอไฟล์ดาวน์โหลด (สูงสุด 3 นาที)...")
                
                for sec in range(1, 181):  # 180 วินาที = 3 นาที
                    current_files = set(glob.glob(os.path.join(CHROME_DOWNLOAD_DIR, 'monthlySales_*.xlsx')))
                    new_files = current_files - initial_files
                    if new_files:
                        downloaded_file = list(new_files)[0]
                        print(f"✨ พบไฟล์ใหม่! {os.path.basename(downloaded_file)} (รอ {sec} วินาที)")
                        break
                    
                    # ทุกๆ 15 วินาที ให้รีเฟรชหน้าเพื่ออัปเดตสถานะ (ตามที่ผู้ใช้แจ้งว่าสถานะไม่อัปเดตถ้าไม่รีเฟรช)
                    if sec % 15 == 0:
                        print(f"   🔄 ครบ {sec} วินาที: กำลังรีเฟรชหน้าเพื่อเช็คสถานะ...")
                        driver.refresh()
                        time.sleep(5) # รอโหลดหน้าใหม่
                        
                        # ลองกดปุ่มดาวน์โหลดใน Task Manager ทันทีหลังรีเฟรช
                        try:
                            # 1. คลิกเปิดประวัติการ Export (ใช้ XPath ที่ผู้ใช้ระบุ)
                            xpath_history = '//*[@id="excelsHistory-area"]/div[1]/div[1]/span[2]'
                            history_btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_history)))
                            driver.execute_script("arguments[0].click();", history_btn)
                            print("   ✅ คลิกเปิดประวัติการ Export สำเร็จ (ตาม XPath)")
                            time.sleep(3) # รอให้รายการโหลดขึ้นมา
                            
                            # 2. หาปุ่มดาวน์โหลดล่าสุดในรายการ
                            driver.execute_script("""
                                var historyArea = document.getElementById('excelsHistory-area');
                                if(historyArea) {
                                    var links = historyArea.querySelectorAll('a');
                                    for(var i=0; i<links.length; i++){
                                        if(links[i].textContent.indexOf('ดาวน์โหลด') !== -1){
                                            links[i].click();
                                            break;
                                        }
                                    }
                                }
                            """)
                        except Exception as e:
                            print(f"   ⚠️ ไม่สามารถคลิกเปิดประวัติ: {e}")
                    
                    time.sleep(1)
                
                if not downloaded_file:
                    print(f"❌ ไม่พบไฟล์หลังรอ 3 นาที (เดือน {m}/{y_be})")
                
                # ===== 7. อัปโหลดไฟล์ไป Google Drive =====
                if downloaded_file:
                    # ใช้ชื่อไฟล์จริงจาก Zort แทนการตั้งชื่อเอง เพื่อความแม่นยำของข้อมูล
                    original_name = os.path.splitext(os.path.basename(downloaded_file))[0]
                    gsheet_name = original_name
                    print(f"📄 เตรียมอัปโหลด (ใช้ชื่อต้นฉบับ): {downloaded_file} -> {gsheet_name}")
                    
                    file_id = upload_and_convert_to_gsheet(downloaded_file, gsheet_name, folder_path="PK/ยอดขาย")
                    if file_id:
                        print(f"🚀 ซิงค์สำเร็จ! ID: {file_id}")
                    
                    if TARGET_DRIVE_FOLDER:
                        if not os.path.exists(TARGET_DRIVE_FOLDER): os.makedirs(TARGET_DRIVE_FOLDER)
                        shutil.copy(downloaded_file, os.path.join(TARGET_DRIVE_FOLDER, f"{gsheet_name}.xlsx"))
                else:
                    print(f"❌ ไม่พบไฟล์ที่ดาวน์โหลดมา (เดือน {m}/{y_be})")

                # รีเฟรชหน้าก่อนทำเดือนถัดไป
                print("🔄 รีเฟรชหน้า...")
                driver.refresh()
                time.sleep(5)
                
            except Exception as inner_e:
                print(f"⚠️ เกิดข้อผิดพลาด: {inner_e}")
                driver.save_screenshot(f"error_sales_{m}_{y_be}.png")
                driver.refresh()
                time.sleep(5)

    except Exception as e:
        print(f"⚠️ เกิดข้อผิดพลาดร้ายแรง: {e}")
        driver.save_screenshot("zort_critical_error.png")
    finally:
        driver.quit()
        print("\n👋 จบการทำงาน")

if __name__ == "__main__":
    run_export()
