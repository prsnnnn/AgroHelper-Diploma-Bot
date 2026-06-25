# -*- coding: utf-8 -*-
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException
from datetime import datetime, timedelta
import io
import base64
from config import token
from database import get_user_role, get_all_inventory, save_log, create_new_user, get_resource_details

bot = telebot.TeleBot(token)


@bot.message_handler(commands=['start'])
def process_start_command(message):
    from database import get_user_role
    tgid = message.from_user.id
    username = message.from_user.first_name
    role = get_user_role(tgid)
    if not role:
        role = create_new_user(tgid, username)
        bot.send_message(tgid,"👋 Вітаємо! Ви були автоматично зареєстровані в системі обліку підприємства. На разі у Вас немає прав. Якщо ви є співробітником - зверніться до адміністратора")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    text_args = message.text.split()
    if len(text_args) > 1 and text_args[1].startswith("wo_"):
        role = get_user_role(tgid)
        if role not in ["admin", "dispatcher", "worker"]:
            bot.send_message(tgid, "⚠️ У вас немає доступу до операцій складу.")
            return

        encoded_name = text_args[1].replace("wo_", "")
        try:
            product_name = base64.b64decode(encoded_name.encode('utf-8')).decode('utf-8')
        except Exception:
            bot.send_message(tgid, "❌ Помилка розпізнавання даних QR-коду.")
            return

        bot.send_message(tgid,'📱')
        res_info = get_resource_details(product_name)
        unit = res_info.get("unit", "шт") if res_info else "шт"
        current_amount = res_info.get("amount", 0.0) if res_info else 0.0
        sent_msg = bot.send_message(
                    tgid,f"📤 *Операція списання (QR)*\n📊 Наразі доступно на складі: *{current_amount} {unit}*\n\nВведіть кількість матеріалу *{product_name}*, яку хочете списати (в одиницях: *{unit}*):",parse_mode="Markdown")
        bot.register_next_step_handler(sent_msg, save_write_off_volume, product_name)
        return
    if role == "admin":
        markup.add(
            types.KeyboardButton("📦 Складські залишки"),
            types.KeyboardButton("📉 Списання ресурсів"),
            types.KeyboardButton("📈 Прихід матеріалів"),
            types.KeyboardButton("📝 Мої логи"),
            types.KeyboardButton('🔑 Адмін панель')
        )
        bot.send_message(tgid,'👨‍💻')
        bot.send_message(
            tgid,
            f"Успішна авторизація, {username}! Оберіть дію:",
            reply_markup=markup
        )
    elif role == "worker":
        markup.add(
            types.KeyboardButton("📦 Складські залишки"),
            types.KeyboardButton("📉 Списання ресурсів"),
            types.KeyboardButton("📈 Прихід матеріалів"),
            types.KeyboardButton("📝 Мої логи"),
        )
        bot.send_message(tgid,'🗂')
        bot.send_message(
            tgid,
            f"Успішна авторизація, {username}! Оберіть дію:",
            reply_markup=markup
        )
    elif role == "guest":
        bot.send_message(tgid,'📬')
        bot.send_message(
            tgid,
            f"{username} Вашу заявку на реєстрацію надіслано адміністратору. Очікуйте підтвердження!",
            reply_markup=markup
        )


@bot.message_handler(func=lambda message: message.text == "📦 Складські залишки")
def process_inventory_view(message):
    tgid = message.from_user.id
    role = get_user_role(tgid)
    if role not in ["admin", "dispatcher",'worker']:
        bot.send_message(tgid, "⚠️ *Доступ обмежено*\nУ вас немає прав для перегляду аналітичних звітів складу.",
                         parse_mode="Markdown")
        return
    items = get_all_inventory()
    if not items:
        bot.send_message(tgid, "📭 *Склад порожній*\nНаразі в базі даних немає зареєстрованих ресурсів.",
                         parse_mode="Markdown")
        return
    categories_titles = {
        "fuel": "⛽ ПАЛЬНО-МАСТИЛЬНІ МАТЕРІАЛИ",
        "fertilizer": "🌱 ДОБРИВА ТА ХІМІКАТИ",
        "seeds": "🌾 ПОСІВНИЙ МАТЕРІАЛ"
    }
    grouped_items = {cat: [] for cat in categories_titles.keys()}
    unknown_items = []
    for item in items:
        cat = item.get("category")
        if cat in grouped_items:
            grouped_items[cat].append(item)
        else:
            unknown_items.append(item)
    report = "📁 *ОПЕРАТИВНИЙ ЗВІТ ПРО СТАН СКЛАДУ*\n"
    report += f"🕒 _Дані актуальні на: {datetime.now().strftime('%d.%m.%Y %H:%M')}_\n"
    report += "▬" * 15 + "\n\n"
    total_positions = 0
    deficit_count = 0
    def get_stock_indicator_and_update(item_obj):
        nonlocal deficit_count
        amount = item_obj.get('amount', 0.0)
        limit = item_obj.get('min_limit', 100.0)

        if amount < limit:
            indicator_icon = "🔴"
            deficit_count += 1
        elif amount <= limit * 3:
            indicator_icon = "🟡"
        else:
            indicator_icon = "🟢"
        return indicator_icon, amount, limit
    for cat_slug, cat_title in categories_titles.items():
        category_products = grouped_items[cat_slug]
        if not category_products:
            continue
        report += f"🔹 **{cat_title}**\n"
        for item in category_products:
            total_positions += 1
            indicator, amount, limit = get_stock_indicator_and_update(item)
            report += f"  {indicator} _{item['resource_name']}_ — *{amount}* {item['unit']} `(ліміт: {limit})`\n"
        report += "\n"
    if unknown_items:
        report += "❓ *ІНШІ МАТЕРІАЛИ*\n"
        for item in unknown_items:
            total_positions += 1
            indicator, amount, limit = get_stock_indicator_and_update(item)
            report += f"  {indicator} _{item['resource_name']}_ — *{amount}* {item['unit']} `(ліміт: {limit})`\n"
        report += "\n"
    report += "▬" * 15 + "\n"
    report += f"📊 Всього найменувань: *{total_positions}*\n"
    if deficit_count > 0:
        report += f"⚠️ Позицій у критичному дефіциті: *{deficit_count}*\n"
    else:
        report += "✅ Всі запаси в межах норми.\n"
    bot.send_message(tgid, '📁')
    bot.send_message(tgid, report, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📈 Прихід матеріалів")
def start_income_process(message):
    tgid = message.from_user.id
    role = get_user_role(tgid)
    if role not in ["admin", "dispatcher",'worker']:
        bot.send_message(message.chat.id, "⚠️ У вас немає прав для оформлення поставок.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⛽ Пально-мастильні матеріали", callback_data="inc_cat:fuel"),
        types.InlineKeyboardButton("🌱 Добрива та хімікати", callback_data="inc_cat:fertilizer"),
        types.InlineKeyboardButton("🌾 Посівний матеріал", callback_data="inc_cat:seeds")
    )
    bot.send_message(message.chat.id,'📈')
    bot.send_message(
        message.chat.id,
        "📈 **Оформлення приходу матеріалів**\nОберіть категорію вантажу, що надійшов:",
        reply_markup=markup,
        parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("inc_cat:"))
def process_category_choice(call):
    category = call.data.split(":")[1]
    from database import get_resources_by_category
    resources = get_resources_by_category(category)
    if not resources:
        bot.answer_callback_query(call.id, "У цій категорії немає товарів")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    for res in resources:
        markup.add(types.InlineKeyboardButton(res["resource_name"], callback_data=f"inc_res:{res['resource_name']}"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📌 Тепер оберіть конкретну номенклатуру позиції:",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_income")
def handle_back_to_income(call):
    start_income_process(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("inc_res:"))
def process_resource_choice(call):
    resource_name = call.data.split(":")[1]
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_income"))
    res_info = get_resource_details(resource_name)
    unit = res_info.get("unit", "шт") if res_info else "шт"
    sent_msg = bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"✍️ Введіть об'єм поставки для позиції *{resource_name}*:\n_(Введіть лише число, наприклад: 250)_\n\n⚠️ Зверніть увагу, значення вводиться в: *{unit}*",
        parse_mode="Markdown",reply_markup=markup
    )
    bot.register_next_step_handler(sent_msg, save_income_volume, resource_name)
    bot.answer_callback_query(call.id)


def save_income_volume(message, resource_name):
    tgid = message.from_user.id
    username = message.from_user.first_name
    input_text = message.text.strip()
    from database import generate_operation_pdf, get_resource_details,add_resource_amount
    try:
        quantity = float(input_text.replace(",", "."))
        if quantity <= 0:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "❌ Помилка! Введене значення має бути додатним числом. Операцію скасовано.")
        return
    new_total = add_resource_amount(resource_name, quantity)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Внести ще один прихід", callback_data="back_to_income"))
    if new_total > 0:
        save_log(tgid, username, "income", resource_name, quantity)
        res_info = get_resource_details(resource_name)
        unit = res_info.get("unit", "шт") if res_info else "шт"
        bot.send_message(
            message.chat.id,
            f"✅ *Поставку успішно оформлено!*\n\n"
            f"📦 Товар: *{resource_name}*\n"
            f"📥 Додано: +{quantity} {unit}\n"
            f"📊 Новий залишок на складі: *{new_total} {unit}*",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        users_to_notify = process_queue_notifications(resource_name)
        for user in users_to_notify:
            try:
                bot.send_message(
                    user["tgid"],
                    f"🔔 **Сповіщення з черги матеріалів!**\n\n"
                    f"На склад щойно надійшла свіжа поставка ресурсу: *{resource_name}*!\n"
                    f"📥 Додано об'єм: `+{quantity}`\n"
                    f"📊 Поточний загальний залишок: *{new_total}*\n\n"
                    f"Ви залишали заявку на: `{user['quantity']}` од. Можете підходити на склад та оформлювати списання через бот або QR-код.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        pdf_file = generate_operation_pdf("income", resource_name, quantity, unit, username, tgid)
        pdf_file.name = f"Akt_Pryjmannya_{int(datetime.now().timestamp())}.pdf"
        bot.send_document(
            message.chat.id,
            pdf_file,
            caption="📄 *Електронна накладна сформована.*\nВи можете завантажити та роздрукувати цей документ для паперової звітності.",
            parse_mode="Markdown"
        )
    else:
        bot.send_message(message.chat.id, "❌ Помилка бази даних. Не вдалося оновити залишок.", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text in ["🔑 Адмін панель"])
def show_admin_panel(message):
    tgid = message.chat.id
    role = get_user_role(tgid)
    if role != "admin":
        bot.send_message(tgid, "⚠️ Доступ заборонено. Ви не є адміністратором.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👥 Обробка заявок (в черзі)", callback_data="admin_view_guests"),
        types.InlineKeyboardButton("👑 Надати права адміністратора (за tgid)", callback_data="admin_promote_user"),
        types.InlineKeyboardButton("🛠️ Редагування персоналу", callback_data="admin_manage_staff"),
        types.InlineKeyboardButton("➕ Додати новий товар в облік", callback_data="admin_add_category"),
        types.InlineKeyboardButton("⚠️ КРИТИЧНІ ЗАЛИШКИ", callback_data="admin_critical_stock"),
        types.InlineKeyboardButton("📊 Економічна оцінка складу", callback_data="admin_finance_calc"),
        types.InlineKeyboardButton("💾 Вивантажити залишки (CSV)", callback_data="admin_export_csv"),
        types.InlineKeyboardButton("📄 Вивантажити останні логи (TXT)", callback_data="get_bot_logs"),)
    bot.send_message(tgid,'🔐')
    bot.send_message(
        tgid,
        "Оберіть необхідну системну дію:",
        reply_markup=markup,
        parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_critical_stock")
def process_critical_stock_view(call):
    from database import get_critical_resources
    critical_items = get_critical_resources()
    if not critical_items:
        bot.answer_callback_query(call.id, "✅ Всі запаси в нормі! Дефіцитних позицій немає.", show_alert=True)
        return
    categories_mapping = {
        "fuel": "⛽ ПАЛЬНО-МАСТИЛЬНІ МАТЕРІАЛИ",
        "fertilizer": "🌱 ДОБРИВА ТА ХІМІКАТИ",
        "seeds": "🌾 ПОСІВНИЙ МАТЕРІАЛ"}
    response = "⚠️ *АНАЛІТИЧНИЙ ЗВІТ: КРИТИЧНІ ЗАЛИШКИ*\n"
    response += "🚨 _Наступні позиції потребують термінової закупівлі!_\n"
    response += "═" * 18 + "\n\n"
    grouped = {}
    for item in critical_items:
        cat = item.get("category", "other")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(item)
    for cat_slug, items_list in grouped.items():
        cat_title = categories_mapping.get(cat_slug, cat_slug.upper())
        response += f"📂 *{cat_title}*\n"
        response += "─" * 15 + "\n"
        for item in items_list:
            amount = item.get("amount", 0.0)
            unit = item.get("unit", "шт")
            limit = item.get("active_limit", 100.0)
            response += (
                f"🔴 *{item['resource_name']}*\n"
                f"   └ Поточний запас: *{amount} {unit}*\n"
                f"   └ Мінімальний поріг: `{limit} {unit}`\n\n")
    response += "═" * 18 + "\n"
    response += "💡 _Порада: Ви можете вивантажити повний CSV-звіт для детального аналізу поставок._"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Назад в адмінку", callback_data="back_to_admin_main"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=response,
        reply_markup=markup,
        parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_view_guests")
def process_view_guests(call):
    from database import get_pending_guests
    guests = get_pending_guests()
    if not guests:
        bot.answer_callback_query(call.id, "🎉 Немає нових заявок на реєстрацію!")
        return
    guest = guests[0]
    guest_tgid = guest["tgid"]
    guest_name = guest["username"]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Схвалити (Worker)", callback_data=f"adm_set:worker:{guest_tgid}"),
        types.InlineKeyboardButton("❌ Відхилити / Бан", callback_data=f"adm_set:block:{guest_tgid}"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"📋 Заявка на реєстрацію:\n\n👤 Ім'я: {guest_name}\n🆔 Telegram ID: `{guest_tgid}`\n\nНадати користувачу доступ з роллю робітника?",
        reply_markup=markup,
        parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_set:"))
def process_role_decision(call):
    _, decision, guest_tgid = call.data.split(":")
    guest_tgid = int(guest_tgid)
    from database import update_user_role, save_log
    if decision == "worker":
        update_user_role(guest_tgid, "worker")
        save_log(call.from_user.id, call.from_user.first_name, "approve_user", f"tgid_{guest_tgid}", 0)
        try:
            bot.send_message(guest_tgid, "🎉 Вітаємо в команді! Адміністратор підтвердив ваш доступ. Введіть /start для оновлення меню.")
        except Exception:
            pass

        msg_text = "✅ Користувача успішно переведено в групу *Worker*."
    else:
        update_user_role(guest_tgid, "blocked")
        msg_text = "❌ Заявку відхилено, користувача заблоковано."
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Наступна заявка", callback_data="admin_view_guests"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=msg_text,
        reply_markup=markup,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_category")
def start_add_product_process(call):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⛽ Пально-мастильні матеріали", callback_data="prod_cat:fuel"),
        types.InlineKeyboardButton("🌱 Добрива та хімікати", callback_data="prod_cat:fertilizer"),
        types.InlineKeyboardButton("🌾 Посівний матеріал", callback_data="prod_cat:seeds"))

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="➕ **Додавання нового товару на склад**\n\nОберіть категорію, до якої належатиме нова позиція:",
        reply_markup=markup,
        parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_staff")
def list_staff_members(call):
    tgid = call.from_user.id
    from database import get_all_staff
    staff = get_all_staff(exclude_tgid=tgid)
    if not staff:
        bot.answer_callback_query(call.id, "ℹ️ У базі даних немає інших працівників.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    role_emojis = {
        "admin": "👑",
        "dispatcher": "🗂️",
        "worker": "🚜",
        "blocked": "⛔"
    }
    for user in staff:
        u_tgid = user["tgid"]
        u_name = user.get("username", f"User_{u_tgid}")
        u_role = user.get("role", "worker")
        emoji = role_emojis.get(u_role, "👤")
        button_text = f"{emoji} {u_name} (ID: {u_tgid})"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"st_view:{u_tgid}"))
    markup.add(types.InlineKeyboardButton("⬅️ Назад в адмінку", callback_data="back_to_admin_main"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="👥 **БАЗА КАДРІВ ПІДПРИЄМСТВА**\n\nОберіть працівника для перегляду профілю або зміни його прав доступу:",
        reply_markup=markup,
        parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("st_view:"))
def view_user_profile(call):
    target_tgid = int(call.data.split(":")[1])
    from database import get_user_by_tgid
    user = get_user_by_tgid(target_tgid)
    if not user:
        bot.answer_callback_query(call.id, "❌ Користувача не знайдено.")
        return
    u_name = user.get("username", "Не вказано")
    u_role = user.get("role", "worker").upper()
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚜 Зробити Worker", callback_data=f"st_ch:{target_tgid}:worker"),
        types.InlineKeyboardButton("🗂️ Зробити Dispatcher", callback_data=f"st_ch:{target_tgid}:dispatcher"))
    markup.add(
        types.InlineKeyboardButton("👑 Зробити Admin", callback_data=f"st_ch:{target_tgid}:admin"),
        types.InlineKeyboardButton("⛔ ЗАБЛОКУВАТИ", callback_data=f"st_ch:{target_tgid}:blocked"))
    markup.add(types.InlineKeyboardButton("⬅️ До списку персоналу", callback_data="admin_manage_staff"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"👤 **ПРОФІЛЬ КОРИСТУВАЧА**\n\n"
             f"📝 Ім'я/Нік: *{u_name}*\n"
             f"🆔 Telegram ID: `{target_tgid}`\n"
             f"📊 Поточна роль: **{u_role}**\n\n"
             f"Оберіть нову роль для користувача або обмежте йому доступ:",
        reply_markup=markup,
        parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("st_ch:"))
def change_user_role_execute(call):
    admin_tgid = call.from_user.id
    admin_name = call.from_user.first_name
    _, target_tgid, new_role = call.data.split(":")
    target_tgid = int(target_tgid)
    from database import update_user_role, save_log
    success = update_user_role(target_tgid, new_role)
    if success:
        save_log(admin_tgid, admin_name, "change_role", f"tgid_{target_tgid}_to_{new_role}", 0)
        try:
            bot.send_message(
                target_tgid,
                f"ℹ️ *Ваш статус у системі змінено!*\nАдміністратор встановив вам роль: *{new_role.upper()}*.\n"
                f"Натисніть /start для оновлення робочого меню."
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id, f"✅ Роль успішно змінено на {new_role.upper()}!")
    else:
        bot.answer_callback_query(call.id, "❌ Помилка оновлення бази даних.")

    list_staff_members(call)


@bot.callback_query_handler(func=lambda call: call.data.startswith("q_join|"))
def handle_join_queue(call):
    tgid = call.from_user.id
    username = call.from_user.first_name
    _, resource_name, quantity = call.data.split("|")
    try:
        quantity = float(quantity)
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Помилка даних", show_alert=True)
        return
    from database import add_to_queue
    expires_at = datetime.now() + timedelta(hours=24)
    inserted = add_to_queue(tgid, username, resource_name, quantity, expires_at)
    if inserted:
        bot.answer_callback_query(call.id, "✅ Вас успішно додано до черги!", show_alert=True)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"⏳ **Ви стали в чергу** на отримання *{quantity}* од. ресурсу *{resource_name}*.\n"
                 f"Система автоматично надішле вам повідомлення, як тільки товар з'явиться на складі.",
            parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "⚠️ Ви вже перебуваєте в активній черзі за цим товаром!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "get_bot_logs")
def export_logs_to_txt(call):
    from database import is_user_admin, fetch_recent_logs
    user_id = call.from_user.id
    if not is_user_admin(user_id):
        bot.answer_callback_query(call.id, "🔴 Доступ заблоковано. У вас немає прав адміністратора.", show_alert=True)
        return
    bot.answer_callback_query(call.id, "⏳ Збираю логи...")
    try:
        log_lines = fetch_recent_logs(limit=2000)
        if not log_lines:
            bot.send_message(call.message.chat.id, "📭 Журнал логів порожній.")
            return
        full_text = "".join(log_lines)
        file_buffer = io.BytesIO(full_text.encode('utf-8'))
        current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_buffer.name = f"Agrohelper_logs_{current_date}.txt"
        bot.send_document(
            chat_id=call.message.chat.id,
            document=file_buffer,
            caption=f"📋 Вивантажено останні {len(log_lines)} логів системи.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Помилка під час генерації файлу: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("prod_cat:"))
def process_product_category_choice(call):
    category = call.data.split(":")[1]
    sent_msg = bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📝 *Введіть назву нового товару*\n\nБудь ласка, напишіть у чат назву позиції:\n_(наприклад: Насіння сої Ультра)_",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(sent_msg, process_product_name_input, category)
    bot.answer_callback_query(call.id)

def process_product_name_input(message, category):
    product_name = message.text.strip()
    tgid = message.from_user.id
    if len(product_name) < 3:
        bot.send_message(tgid, "❌ Назва надто коротка. Процес скасовано.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("тонни (т)", callback_data=f"unit:т:{category}:{product_name}"),
        types.InlineKeyboardButton("кілограми (кг)", callback_data=f"unit:кг:{category}:{product_name}"),
        types.InlineKeyboardButton("літри (л)", callback_data=f"unit:л:{category}:{product_name}"),
        types.InlineKeyboardButton("мішки (міш.)", callback_data=f"unit:міш.:{category}:{product_name}"),
        types.InlineKeyboardButton("штуки (шт)", callback_data=f"unit:шт:{category}:{product_name}"))
    bot.send_message(
        tgid,
        f"📐 *Одиниці виміру для товару:*\n«_{product_name}_»\n\nОберіть базову одиницю обліку:",
        reply_markup=markup,
        parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("unit:"))
def process_product_unit_choice(call):
    data_parts = call.data.split(":")
    unit = data_parts[1]
    category = data_parts[2]
    product_name = data_parts[3]
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

    sent_msg = bot.send_message(
        chat_id=call.message.chat.id,
        text=f"⚠️ **Встановлення ліміту для алерту**\n\n"
             f"Який мінімальний запас (`min_limit`) виставити для позиції *{product_name}*?\n"
             f"_(Якщо залишок впаде нижче цього числа, адмінам прийде сповіщення. Введіть лише число, наприклад: 50)_",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(sent_msg, save_new_product_with_limit, category, product_name, unit)
    bot.answer_callback_query(call.id)

def save_new_product_with_limit(message, category, product_name, unit):
    tgid = message.from_user.id
    username = message.from_user.first_name
    input_text = message.text.strip()
    try:
        min_limit = float(input_text.replace(",", "."))
        if min_limit < 0:
            raise ValueError
    except ValueError:
        bot.send_message(tgid, "❌ Помилка! Значення критичного залишку має бути додатним числом. Операцію скасовано.")
        return
    from database import insert_new_product, save_log
    success = insert_new_product(category, product_name, unit, min_limit)
    if success:
        save_log(tgid, username, "add_product", f"{product_name} ({unit}, ліміт: {min_limit})", 0.0)
        BOT_USERNAME = "agrooohelp_bot"
        from database import generate_product_qr
        qr_file = generate_product_qr(product_name, BOT_USERNAME)
        qr_file.name = f"QR_{product_name}.png"
        bot.send_message(
            chat_id=message.chat.id,
            text=f"✅ **Товар успішно створено!**\n\n"
                 f"📦 Назва: *{product_name}*\n"
                 f"📐 Одиниця обліку: *{unit}*\n"
                 f"⚠️ Критичний ліміт: **{min_limit} {unit}**",
            parse_mode="Markdown")
        bot.send_photo(
            chat_id=message.chat.id,
            photo=qr_file,
            caption=f"🖨 **QR-код для швидкого списання**\n\nРоздрукуйте та наклейте на локацію з матеріалом: *{product_name}*.\nПри скануванні працівник одразу перейде до введення об'єму списання.",
            parse_mode="Markdown")
    else:
        bot.send_message(
            chat_id=message.chat.id,
            text=f"❌ **Помилка створення!**\nТовар з назвою *{product_name}* вже існує в базі даних.",
            parse_mode="Markdown"
        )

@bot.callback_query_handler(func=lambda call: call.data == "admin_promote_user")
def start_promotion_process(call):
    sent_msg = bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="👑 **Призначення нового адміністратора**\n\nБудь ласка, введіть Telegram ID (`tgid`) користувача, якому хочете надати повний доступ:\n_(Введіть лише цифри, наприклад: 987654321)_",
        parse_mode="Markdown")
    bot.register_next_step_handler(sent_msg, process_admin_tgid_input)
    bot.answer_callback_query(call.id)

def process_admin_tgid_input(message):
    current_admin_tgid = message.from_user.id
    input_text = message.text.strip()
    if not input_text.isdigit():
        bot.send_message(
            message.chat.id,
            "❌ **Помилка введення!** ID має складатися виключно з цифр. Операцію скасовано.")
        return
    target_tgid = int(input_text)
    if target_tgid == current_admin_tgid:
        bot.send_message(message.chat.id, "ℹ️ Ви вже є адміністратором цієї системи.")
        return
    from database import promote_to_admin, save_log
    db_status_message = promote_to_admin(target_tgid)
    save_log(current_admin_tgid, message.from_user.first_name, "promote_admin", f"target_tgid_{target_tgid}", 0)
    bot.send_message(
        message.chat.id,
        f"👑 **Системні права оновлено!**\n\n"
        f"🆔 Цільовий користувач: `{target_tgid}`\n"
        f"📊 Статус бази даних: _{db_status_message}_\n\n"
        f"При наступному натисканні `/start` цей користувач отримає доступ до Адмін-панелі.",
        parse_mode="Markdown")
    try:
        bot.send_message(
            target_tgid,
            "👑 **Увага!** Адміністратор надав вам права [admin] системи обліку. "
            "\nПерезапустіть бота командою /start для доступу до панелі керування.")
    except Exception:
        pass

@bot.message_handler(func=lambda message: message.text == "📉 Списання ресурсів")
def start_write_off_process(message):
    tgid = message.from_user.id
    role = get_user_role(tgid)
    if role not in ["admin", "dispatcher", "worker"]:
        bot.send_message(tgid, "⚠️ Доступ обмежено. Зверніться до адміністратора.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⛽ Пально-мастильні матеріали", callback_data="wo_cat:fuel"),
        types.InlineKeyboardButton("🌱 Добрива та хімікати", callback_data="wo_cat:fertilizer"),
        types.InlineKeyboardButton("🌾 Посівний матеріал", callback_data="wo_cat:seeds"))
    bot.send_message(tgid,'📉')
    bot.send_message(
        tgid,
        "*Оформлення списання (видачі) ресурсів*\nОберіть категорію матеріалу, який ви берете:",
        reply_markup=markup,
        parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("wo_cat:"))
def process_wo_category_choice(call):
    category = call.data.split(":")[1]
    from database import get_resources_by_category
    resources = get_resources_by_category(category)
    if not resources:
        bot.answer_callback_query(call.id, "У цій категорії поки немає товарів")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    for res in resources:
        markup.add(types.InlineKeyboardButton(res["resource_name"], callback_data=f"wo_res:{res['resource_name']}"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📌 Оберіть конкретний товар для списання:",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("wo_res:"))
def process_wo_resource_choice(call):
    resource_name = call.data.split(":")[1]
    res_info = get_resource_details(resource_name)
    unit = res_info.get("unit", "шт") if res_info else "шт"
    current_amount = res_info.get("amount", 0.0) if res_info else 0.0
    sent_msg = bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"📤 *Операція списання*\n📊 Наразі доступно на складі: *{current_amount} {unit}*\n\nВведіть кількість матеріалу *{resource_name}*, яку хочете списати (в одиницях: *{unit}*):",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(sent_msg, save_write_off_volume, resource_name)
    bot.answer_callback_query(call.id)

def save_write_off_volume(message, resource_name):
    tgid = message.from_user.id
    username = message.from_user.first_name
    input_text = message.text.strip()
    try:
        quantity = float(input_text.replace(",", "."))
        if quantity <= 0:
            raise ValueError
    except ValueError:
        bot.send_message(tgid, "❌ Помилка! Введене значення має бути додатним числом. Операцію скасовано.")
        return
    from database import write_off_resource, save_log, generate_operation_pdf
    updated_resource = write_off_resource(resource_name, quantity)
    if not updated_resource:
        markup_ = types.InlineKeyboardMarkup()
        btn_queue = types.InlineKeyboardButton(
            text="⏳ Стати в чергу на 24 години",
            callback_data=f"q_join|{resource_name}|{quantity}"
        )
        markup_.add(btn_queue)
        res_info = get_resource_details(resource_name)
        unit = res_info.get("unit", "шт") if res_info else "шт"
        current_amount = res_info.get("amount", 0.0) if res_info else 0.0
        bot.send_message(
            tgid,
            f"❌ Недостатньо товару на складі!\n"
            f"Ви намагаєтесь списати: {quantity} {unit}\n"
            f"Фактично доступно: {current_amount} {unit}\n\n"
            f"Бажаєте стати в чергу на отримання цього об'єму?",
            reply_markup=markup_
        )
        return
    save_log(tgid, username, "write_off", resource_name, quantity)
    new_total = updated_resource["amount"]
    unit = updated_resource["unit"]
    bot.send_message(
        tgid,
        f"✅ *Ресурс успішно списано!*\n\n"
        f"📦 Товар: *{resource_name}*\n"
        f"📉 Видано: -{quantity} {unit}\n"
        f"📊 Актуальний залишок: *{new_total}* {unit}",
        parse_mode="Markdown"
    )
    critical_threshold = updated_resource.get("min_limit", 100.0)
    if new_total < critical_threshold:
        from database import users_col
        admins = list(users_col.find({"role": "admin"}))
        alert_text = f"⚠️ *🚨 СИСТЕМНИЙ АЛЕРТ: ДЕФІЦИТ РЕСУРСУ!*\n\n" \
                     f"На складі критично знизився рівень позиції: *{resource_name}*!\n" \
                     f"📉 Поточний залишок: *{new_total} {unit}* (менше критичного порогу {critical_threshold} {unit})\n" \
                     f"👤 Останнє списання виконав: {username} (ID: `{tgid}`)\n\n" \
                     f"Рекомендується терміново оформити закупівлю."
        for admin in admins:
            try:
                bot.send_message(admin["tgid"], alert_text, parse_mode="Markdown")
            except Exception:
                pass
    pdf_file = generate_operation_pdf("write_off", resource_name, quantity, unit, username, tgid)
    pdf_file.name = f"Nakladna_Spysannya_{resource_name}_{int(datetime.now().timestamp())}.pdf"
    bot.send_document(
        tgid,
        pdf_file,
        caption="📄 *Акт списання/видачі сформовано.*\nЗбережіть цей документ для підтвердження отримання матеріалів матеріально відповідальною особою.",
        parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📝 Мої логи")
def show_personal_history(message):
    tgid = message.from_user.id
    from database import get_user_logs
    logs = get_user_logs(tgid, limit=5)
    if not logs:
        bot.send_message(tgid, "ℹ️ Ви ще не проводили жодних операцій через цього бота.")
        return
    response = "📝 *ВАША ІСТОРІЯ ОСТАННІХ ДІЙ:*\n\n"
    for log in logs:
        action = log.get("action", "unknown")
        if action == "income":
            action_type = "📥 Прихід"
        elif action == "write_off":
            action_type = "📉 Списання"
        elif action == "promote_admin":
            action_type = "👑 Призначив адміна"
        elif action == "add_product":
            action_type = "➕ Додав товар"
        else:
            action_type = "⚙️ Операція"
        details = log.get("details")
        if not details:
            res_name = log.get("resource", "Ресурс")
            qty = log.get("quantity", 0.0)
            if qty > 0:
                details = f"{res_name} ({qty})"
            else:
                details = "системні зміни"
        timestamp = log.get("timestamp")
        date_str = timestamp.strftime("%d.%m %H:%M") if timestamp else "??.??"
        response += f"▫️ `[{date_str}]` {action_type}: *{details}*\n"
    bot.send_message(tgid,'📝')
    bot.send_message(tgid, response, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_finance_calc")
def process_finance_calculation(call):
    from database import calculate_detailed_warehouse_value
    total_sum, report_data = calculate_detailed_warehouse_value()
    categories_titles = {
        "fuel": "⛽ ПАЛЬНО-МАСТИЛЬНІ МАТЕРІАЛИ",
        "fertilizer": "🌱 ДОБРИВА ТА ХІМІКАТИ",
        "seeds": "🌾 ПОСІВНИЙ МАТЕРІАЛ",
        "other": "📦 ІНШІ МАТЕРІАЛИ"
    }
    response = "💰 *ФІНАНСОВА ОЦІНКА СКЛАДУ*\n"
    response += "═" * 18 + "\n\n"
    for cat_slug, cat_info in report_data.items():
        if not cat_info["items"]:
            continue
        cat_title = categories_titles.get(cat_slug, cat_slug.upper())
        response += f"📂 *{cat_title}*\n"
        response += "─" * 15 + "\n"
        for item in cat_info["items"]:
            response += (
                f"▫️ *{item['name']}*\n"
                f"   └ Залишок: {item['amount']} {item['unit']} × {item['price']:,.0f} грн/од\n"
                f"   └ Вартість: `{item['total_cost']:,.2f} грн.`\n"
            )
        response += f"🔹 *Разом по категорії:* __{cat_info['category_total']:,.2f} грн.__\n\n"

    response += "═" * 18 + "\n"
    response += f"🔥 *ЗАГАЛЬНА ВАРТІСТЬ УСІХ АКТИВІВ:*\n💰 *{total_sum:,.2f} грн.*\n\n"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Назад в адмінку", callback_data="back_to_admin_main"))

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=response,
        reply_markup=markup,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "admin_export_csv")
def process_csv_export(call):
    tgid = call.from_user.id
    from database import get_all_inventory, generate_inventory_csv
    bot.send_message(tgid,'💬')
    items = get_all_inventory()
    if not items:
        bot.answer_callback_query(call.id, "❌ Немає даних для експорту")
        return
    categories_mapping = {
        "fuel": "Пально-мастильні матеріали",
        "fertilizer": "Добрива та хімікати",
        "seeds": "Посівний матеріал"}
    buf = generate_inventory_csv(items, categories_mapping)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except ApiTelegramException:
        pass
    bot.send_document(
        tgid,
        buf,
        caption="📊 *Звіт сформовано успішно!*",
        parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_admin_main")
def back_to_admin(call):
    show_admin_panel(call.message)
    bot.answer_callback_query(call.id)


if __name__ == '__main__':
    try:
        print("Бот запущений та готовий до обробки транзакцій...")
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("Зупинено користувачем")
    except Exception as e:
        print(f'Unexpected error: {e}')