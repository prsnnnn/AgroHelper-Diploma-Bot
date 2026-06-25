from pymongo import MongoClient
from datetime import datetime
from config import MONGO_token
import io
from fpdf import FPDF
import base64
import qrcode
import csv


client = MongoClient(MONGO_token)
db = client["agro_db"]


users_col = db["users"]
inventory_col = db["inventory"]
logs_col = db["logs"]
queue_col = db["queue"]
queue_col.create_index("expires_at", expireAfterSeconds=0)

def get_user_role(tgid: int) -> str | None:
    user = users_col.find_one({"tgid": tgid})
    return user.get("role") if user else None


def create_new_user(tgid: int, username: str) -> str:
    default_role = "guest"
    new_user_doc = {
        "tgid": tgid,
        "username": username,
        "role": default_role,
        "registered_at": datetime.now()}
    users_col.insert_one(new_user_doc)
    save_log(tgid, username, "registration", "system_access", 0.0)
    return default_role

def get_all_inventory() -> list:
    return list(inventory_col.find({}))

def update_resource_amount(resource_name: str, quantity: float, operation_type: str) -> bool:
    resource = inventory_col.find_one({"resource_name": resource_name})
    if not resource:
        return False
    current_amount = resource["amount"]
    if operation_type == "write_off":
        if current_amount < quantity:
            return False
        new_amount = current_amount - quantity
    else:
        new_amount = current_amount + quantity
    inventory_col.update_one(
        {"resource_name": resource_name},
        {"$set": {"amount": new_amount}})
    return True

def save_log(tgid: int, username: str, action: str, resource: str, quantity: float):
    log_document = {
        "timestamp": datetime.now(),
        "tgid": tgid,
        "username": username,
        "action": action,
        "resource": resource,
        "quantity": quantity}
    logs_col.insert_one(log_document)


def get_resources_by_category(category: str) -> list:
    return list(inventory_col.find({"category": category}))

def generate_inventory_csv(items, categories_mapping) -> io.BytesIO:
    csv_file = io.StringIO()
    writer = csv.writer(csv_file, delimiter=';', lineterminator='\n')
    writer.writerow(["Категорія", "Назва товару", "Поточний залишок", "Одиниця виміру"])
    for item in items:
        raw_cat = item.get("category", "other")
        category_beautiful = categories_mapping.get(raw_cat, raw_cat.upper())
        name = item.get("resource_name", "Незрозумілий товар")
        amount = str(item.get("amount", 0.0)).replace('.', ',')
        unit = item.get("unit", "шт")
        writer.writerow([category_beautiful, name, amount, unit])
    buf = io.BytesIO(csv_file.getvalue().encode('utf-8-sig'))
    buf.name = f"Склад_Залишки_{datetime.now().strftime('%d_%m_%Y')}.csv"
    return buf

def add_resource_amount(resource_name: str, quantity: float) -> float:
    resource = inventory_col.find_one({"resource_name": resource_name})
    if not resource:
        return 0.0
    new_amount = resource["amount"] + quantity
    inventory_col.update_one(
        {"resource_name": resource_name},
        {"$set": {"amount": new_amount}})
    return new_amount

def get_pending_guests() -> list:
    return list(users_col.find({"role": "guest"}))

def update_user_role(user_tgid: int, new_role: str) -> bool:
    result = users_col.update_one(
        {"tgid": user_tgid},
        {"$set": {"role": new_role}})
    return result.modified_count > 0

def add_new_category_to_db(category_slug: str, category_title: str):
    inventory_col.insert_one({
        "category": category_slug,
        "resource_name": f"Тестовий товар ({category_title})",
        "amount": 0.0,
        "unit": "шт"})

def insert_new_product(category: str, product_name: str, unit: str, min_limit: float) -> bool:
    exists = inventory_col.find_one({"resource_name": product_name})
    if exists:
        return False
    new_product_doc = {
        "category": category,
        "resource_name": product_name,
        "amount": 0.0,
        "unit": unit,
        "min_limit": min_limit}
    inventory_col.insert_one(new_product_doc)
    return True

def promote_to_admin(target_tgid: int) -> str:
    user = users_col.find_one({"tgid": target_tgid})
    if user:
        users_col.update_one({"tgid": target_tgid}, {"$set": {"role": "admin"}})
        return f"Права існуючого користувача (роль: {user.get('role')}) успішно підвищено до Admin."
    else:
        users_col.insert_one({
            "tgid": target_tgid,
            "username": "Promoted_by_Admin",
            "role": "admin",
            "registered_at": datetime.now()})
        return "Створено новий профіль. Користувачу успішно надано роль Admin."

def write_off_resource(resource_name: str, quantity: float) -> dict | None:
    resource = inventory_col.find_one({"resource_name": resource_name})
    if not resource:
        return None
    current_amount = resource["amount"]
    if current_amount < quantity:
        return None
    new_amount = current_amount - quantity
    inventory_col.update_one(
        {"resource_name": resource_name},
        {"$set": {"amount": new_amount}})
    resource["amount"] = new_amount
    return resource

def get_user_logs(user_tgid: int, limit: int = 5) -> list:
    return list(logs_col.find({"tgid": user_tgid}).sort("timestamp", -1).limit(limit))

def calculate_detailed_warehouse_value() -> tuple[float, dict]:
    items = list(inventory_col.find({}))
    prices = {
        "Дизельне пальне": 55.0,
        "Бензин А-92": 52.0,
        "Моторна олива": 220.0,
        "Аміачна селітра": 18000.0,
        "Нітроамофоска": 24000.0,
        "Гербіцид Раундап": 350.0,
        "Насіння кукурудзи": 3200.0,
        "Насіння соняшника": 4100.0,
        "Озима пшениця": 8500.0}
    total_warehouse_value = 0.0
    report_data = {
        "fuel": {"items": [], "category_total": 0.0},
        "fertilizer": {"items": [], "category_total": 0.0},
        "seeds": {"items": [], "category_total": 0.0},
        "other": {"items": [], "category_total": 0.0}}
    for item in items:
        name = item.get("resource_name", "Невідомий товар")
        category = item.get("category", "other")
        amount = item.get("amount", 0.0)
        unit = item.get("unit", "шт")
        price = prices.get(name, 100.0)
        item_cost = amount * price
        total_warehouse_value += item_cost
        if category not in report_data:
            report_data[category] = {"items": [], "category_total": 0.0}
        report_data[category]["items"].append({
            "name": name,
            "amount": amount,
            "unit": unit,
            "price": price,
            "total_cost": item_cost})
        report_data[category]["category_total"] += item_cost
    return total_warehouse_value, report_data

def generate_operation_pdf(action_type: str, resource_name: str, quantity: float, unit: str, username: str, tgid: int) -> io.BytesIO:
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font('Arial', '', 'Arial.ttf')
    pdf.set_font('Arial', '', 12)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 5, txt="СТРУКТУРНИЙ ПІДРОЗДІЛ: ЦЕНТРАЛЬНИЙ СКЛАД АГРОКОМПЛЕКСУ", ln=True, align='L')
    pdf.cell(0, 5, txt=f"ДАТА/ЧАС: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}", ln=True, align='L')
    pdf.ln(10)
    pdf.set_font('Arial', '', 16)
    doc_id = int(datetime.now().timestamp())
    if action_type == "income":
        title = f"АКТ ПРИЙМАННЯ МАТЕРІАЛІВ № {doc_id}"
    else:
        title = f"НАКЛАДНА НА СПИСАННЯ/ВИДАЧУ № {doc_id}"
    pdf.cell(0, 10, txt=title, ln=True, align='C')
    pdf.ln(10)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 7, txt=f"Цим документом засвідчується проведення операції в системі обліку.", ln=True)
    pdf.cell(0, 7, txt=f"Відповідальна особа (оператор): {username} (Telegram ID: {tgid})", ln=True)
    pdf.ln(5)
    pdf.set_fill_color(230, 230, 230)  # Сірий фон для шапки таблиці
    pdf.cell(90, 10, txt=" Назва матеріалу / Номенклатура", border=1, fill=True)
    pdf.cell(45, 10, txt=" Кількість", border=1, fill=True, align='C')
    pdf.cell(45, 10, txt=" Од. виміру", border=1, fill=True, align='C')
    pdf.ln()
    pdf.cell(90, 10, txt=f" {resource_name}", border=1)
    pdf.cell(45, 10, txt=f" {quantity}", border=1, align='C')
    pdf.cell(45, 10, txt=f" {unit}", border=1, align='C')
    pdf.ln(20)
    pdf.cell(0, 7, txt="Здав (матеріально відповідальна особа):  _______________________", ln=True)
    pdf.ln(3)
    pdf.cell(0, 7, txt="Прийняв (комірник / водій):            _______________________", ln=True)
    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    return pdf_output

def get_all_staff(exclude_tgid: int) -> list:
    return list(users_col.find({
        "tgid": {"$ne": exclude_tgid},
        "role": {"$in": ["worker", "dispatcher", "blocked", "admin"]}}))

def get_user_by_tgid(target_tgid: int) -> dict | None:
    return users_col.find_one({"tgid": target_tgid})

def generate_product_qr(product_name: str, bot_username: str) -> io.BytesIO:
    encoded_name = base64.b64encode(product_name.encode('utf-8')).decode('utf-8')
    link = f"https://t.me/{bot_username}?start=wo_{encoded_name}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    qr_output = io.BytesIO()
    img.save(qr_output, format="PNG")
    qr_output.seek(0)
    return qr_output

def is_user_admin(telegram_id):
    user = users_col.find_one({"tgid": telegram_id, "role": "admin"})
    return user is not None

def fetch_recent_logs(limit=2000):
    logs_cursor = logs_col.find().sort("timestamp", -1).limit(limit)
    log_lines = []
    for log in logs_cursor:
        ts = log.get("timestamp")
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else str(ts)
        u_id = log.get("tgid", "Невстановлено")
        action = log.get("action", "Дія відсутня")
        resource = log.get("resource", "-")
        quantity=log.get("quantity", "-")
        line = f"[{time_str}] [ID: {u_id}] | Операція: {action} | Деталі: {resource} | Кількість: {quantity}\n\n"
        log_lines.append(line)
    return log_lines

def get_critical_resources() -> list:
    items = list(inventory_col.find({}))
    critical_items = []
    for item in items:
        limit = item.get("min_limit", 100.0)
        if item.get("amount", 0.0) < limit:
            item["active_limit"] = limit
            critical_items.append(item)
    return critical_items

def get_resource_details(resource_name: str) -> dict | None:
    return inventory_col.find_one({"resource_name": resource_name})

def add_to_queue(tgid: int, username: str, resource_name: str, quantity: float, expires_at: datetime) -> bool:
    existing = queue_col.find_one({
        "tgid": tgid,
        "resource_name": resource_name,
        "status": "waiting"})
    if existing:
        return False
    queue_col.insert_one({
        "tgid": tgid,
        "username": username,
        "resource_name": resource_name,
        "quantity": quantity,
        "created_at": datetime.now(),
        "expires_at": expires_at,
        "status": "waiting"})
    return True

def process_queue_notifications(resource_name: str) -> list:
    query = {
        "resource_name": resource_name,
        "status": "waiting",
        "expires_at": {"$gt": datetime.now()}}
    waiting_users = list(queue_col.find(query))
    if waiting_users:
        queue_col.update_many(query, {"$set": {"status": "notified"}})
    return waiting_users