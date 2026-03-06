# PK Cargo Scraper (GitHub Actions Edition)

สคริปต์สำหรับดึงข้อมูล PK Cargo อัตโนมัติและเก็บบันทึกบน GitHub โดยตรง

## การตั้งค่า (Setup)
1. นำข้อมูลในโฟลเดอร์นี้ทั้งหมดไปสร้าง **New Private Repository** บน GitHub
2. ไปที่ **Settings** > **Secrets and variables** > **Actions**
3. เพิ่ม **New repository secret** ดังนี้:
   - `PK_EMAIL`: อีเมลที่ใช้เข้าระบบ PK Cargo
   - `PK_PASSWORD`: รหัสผ่านที่ใช้เข้าระบบ PK Cargo
4. ไปที่ tab **Actions** แล้วลองกดรัน **"Daily PK Cargo Scrape"** เพื่อทดสอบดูว่าข้อมูลถูกดึงมาจริงไหม

## วิธีการทำงาน
- ทุกๆ 6 ชั่วโมง ระบบจะรัน `scraper.py` บนระบบคลาวด์ของ GitHub
- หลังจากดึงข้อมูลเสร็จ ระบบจะอัปเดตไฟล์ `pkcargo_data.json` เข้าสู่โปรเจกต์ของคุณโดยอัตโนมัติ
- ข้อมูลที่อยู่ใน GitHub นี้สามารถนำไปใช้เป็น Source สำหรับ Dashboard ออนไลน์ได้

## โครงสร้าง
- `scraper.py`: ตัวหลักที่รันบน GitHub
- `.github/workflows/scrape.yml`: ตัวกำหนดเวลาให้รันอัตโนมัติ
- `pkcargo_data.json`: ผลลัพธ์ข้อมูลที่จะได้
