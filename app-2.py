"""
🛒 بوت متجر تيليغرام + داشبورد ويب
=====================================
ملف واحد كامل — جاهز للرفع على fps.ms
"""

# ══════════════════════════════════════
#  📦  المكتبات
# ══════════════════════════════════════
import logging
import sqlite3
import json
import threading
import os
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

# ══════════════════════════════════════
#  ⚙️  الإعدادات — غيّر هذي القيم فقط
# ══════════════════════════════════════
TOKEN           = "ضع_توكن_البوت_هنا"
ADMIN_IDS       = [123456789]        # ضع Telegram ID تبتاعك
DASHBOARD_PASS  = "admin1234"        # كلمة مرور الداشبورد — غيّرها!
DB_FILE         = "store.db"
CURRENCY        = "IQD"
MINIAPP_URL     = "https://اسم_حسابك.github.io/اسم_الريبو/miniapp.html"  # ← غيّر هذا لاحقاً

# ══════════════════════════════════════
#  📋  حالات المحادثة
# ══════════════════════════════════════
(
    A_PROD_NAME, A_PROD_DESC, A_PROD_PRICE,
    A_PROD_STOCK, A_PROD_IMAGE,
    A_EDIT_FIELD, A_EDIT_VALUE,
    C_NAME, C_PHONE, C_ADDRESS
) = range(10)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ══════════════════════════════════════
#  🗄️  قاعدة البيانات
# ══════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                description TEXT,
                price       REAL    NOT NULL,
                stock       INTEGER NOT NULL DEFAULT 0,
                image_id    TEXT,
                active      INTEGER DEFAULT 1,
                created_at  TEXT    DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                cust_name   TEXT,
                phone       TEXT,
                address     TEXT,
                items_json  TEXT,
                total       REAL,
                status      TEXT    DEFAULT 'pending',
                created_at  TEXT    DEFAULT (datetime('now'))
            );
        """)

# ══════════════════════════════════════
#  🔧  دوال مساعدة
# ══════════════════════════════════════
def is_admin(user_id): return user_id in ADMIN_IDS
def fmt_price(amount): return f"{amount:,.0f} {CURRENCY}"
def get_cart(context): return context.user_data.setdefault("cart", {})

def cart_total(cart):
    with get_db() as db:
        total = 0.0
        for pid, qty in cart.items():
            row = db.execute("SELECT price FROM products WHERE id=?", (pid,)).fetchone()
            if row: total += row["price"] * qty
    return total

def cart_summary(cart):
    if not cart: return "🛒 السلة فارغة"
    lines = ["🛒 *سلتك:*\n"]
    with get_db() as db:
        for pid, qty in cart.items():
            row = db.execute("SELECT name, price FROM products WHERE id=?", (pid,)).fetchone()
            if row:
                lines.append(f"• {row['name']} × {qty} — {fmt_price(row['price'] * qty)}")
    lines.append(f"\n💰 *الإجمالي: {fmt_price(cart_total(cart))}*")
    return "\n".join(lines)

def order_status_ar(status):
    return {
        "pending":    "⏳ قيد الانتظار",
        "confirmed":  "✅ مؤكّد",
        "processing": "🔧 قيد التجهيز",
        "shipping":   "🚚 قيد التوصيل",
        "delivered":  "📦 تم التسليم",
        "cancelled":  "❌ ملغي",
    }.get(status, status)

# ══════════════════════════════════════
#  🏠  القائمة الرئيسية
# ══════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await admin_main_menu(update, context)
    else:
        await customer_main_menu(update, context)

async def customer_main_menu(update, context):
    kb = [
        [InlineKeyboardButton("🛍️ تصفح المنتجات", callback_data="browse")],
        [InlineKeyboardButton("🛒 سلتي", callback_data="view_cart"),
         InlineKeyboardButton("📦 طلباتي", callback_data="my_orders")],
    ]
    text = "👋 أهلاً بك في متجرنا!\nاختر ما تريد:"
    markup = InlineKeyboardMarkup(kb)
    if update.message:
        await update.message.reply_text(text, reply_markup=markup)
    else:
        await update.callback_query.edit_message_text(text, reply_markup=markup)

async def admin_main_menu(update, context):
    kb = [
        [InlineKeyboardButton("📦 إدارة المنتجات", callback_data="admin_products")],
        [InlineKeyboardButton("📋 الطلبات",         callback_data="admin_orders")],
        [InlineKeyboardButton("📊 الإحصائيات",      callback_data="admin_stats")],
        [InlineKeyboardButton("🛍️ واجهة الزبون",   callback_data="browse")],
    ]
    text = "⚙️ *لوحة الأدمن*"
    markup = InlineKeyboardMarkup(kb)
    if update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

# ══════════════════════════════════════
#  🛍️  تصفح المنتجات
# ══════════════════════════════════════
async def browse_products(update, context):
    query = update.callback_query
    await query.answer()
    with get_db() as db:
        products = db.execute(
            "SELECT * FROM products WHERE active=1 AND stock>0 ORDER BY id"
        ).fetchall()
    if not products:
        await query.edit_message_text("😔 لا توجد منتجات متاحة حالياً.")
        return
    context.user_data["browse_index"] = 0
    await show_product(query, context, products, 0)

async def show_product(query, context, products, index):
    p = products[index]
    cart = get_cart(context)
    in_cart = cart.get(str(p["id"]), 0)
    text = (
        f"*{p['name']}*\n\n"
        f"📝 {p['description'] or 'لا يوجد وصف'}\n\n"
        f"💰 السعر: {fmt_price(p['price'])}\n"
        f"📦 المخزون: {p['stock']} قطعة\n"
    )
    if in_cart: text += f"\n🛒 في سلتك: {in_cart} قطعة"
    kb = []
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"prod_{index-1}"))
    if index < len(products) - 1:
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"prod_{index+1}"))
    if nav: kb.append(nav)
    kb.append([
        InlineKeyboardButton("➕ أضف للسلة", callback_data=f"addcart_{p['id']}"),
        InlineKeyboardButton("🛒 السلة", callback_data="view_cart"),
    ])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    context.user_data["products_list"] = [dict(row) for row in products]
    markup = InlineKeyboardMarkup(kb)
    if p["image_id"]:
        try:
            await query.message.reply_photo(photo=p["image_id"], caption=text, reply_markup=markup, parse_mode="Markdown")
            await query.message.delete()
        except:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

async def navigate_product(update, context):
    query = update.callback_query
    await query.answer()
    index = int(query.data.split("_")[1])
    products_data = context.user_data.get("products_list", [])
    if not products_data:
        await query.edit_message_text("انتهت الجلسة، ابدأ من جديد.")
        return
    class FakeRow(dict):
        def __getitem__(self, key): return super().__getitem__(key)
    await show_product(query, context, [FakeRow(p) for p in products_data], index)

# ══════════════════════════════════════
#  🛒  السلة
# ══════════════════════════════════════
async def add_to_cart(update, context):
    query = update.callback_query
    await query.answer("✅ تمت الإضافة!")
    pid = query.data.split("_")[1]
    cart = get_cart(context)
    cart[pid] = cart.get(pid, 0) + 1

async def view_cart(update, context):
    query = update.callback_query
    await query.answer()
    cart = get_cart(context)
    text = cart_summary(cart)
    kb = []
    if cart:
        kb.append([InlineKeyboardButton("✅ إتمام الطلب", callback_data="checkout")])
        kb.append([InlineKeyboardButton("🗑️ إفراغ السلة", callback_data="clear_cart")])
    kb.append([InlineKeyboardButton("🛍️ متابعة التسوق", callback_data="browse")])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def clear_cart(update, context):
    query = update.callback_query
    await query.answer("🗑️ تم إفراغ السلة")
    context.user_data["cart"] = {}
    await view_cart(update, context)

# ══════════════════════════════════════
#  📝  إتمام الطلب
# ══════════════════════════════════════
async def checkout_start(update, context):
    query = update.callback_query
    await query.answer()
    if not get_cart(context):
        await query.edit_message_text("🛒 السلة فارغة!")
        return ConversationHandler.END
    await query.edit_message_text("📝 لإتمام طلبك، أحتاج بعض المعلومات.\n\n👤 اكتب اسمك الكامل:")
    return C_NAME

async def checkout_name(update, context):
    context.user_data["order_name"] = update.message.text
    await update.message.reply_text("📱 اكتب رقم هاتفك:")
    return C_PHONE

async def checkout_phone(update, context):
    context.user_data["order_phone"] = update.message.text
    await update.message.reply_text("📍 اكتب عنوان التوصيل (المحافظة / المنطقة / التفاصيل):")
    return C_ADDRESS

async def checkout_address(update, context):
    context.user_data["order_address"] = update.message.text
    cart = get_cart(context)
    text = (
        f"{cart_summary(cart)}\n\n"
        f"👤 الاسم: {context.user_data['order_name']}\n"
        f"📱 الهاتف: {context.user_data['order_phone']}\n"
        f"📍 العنوان: {context.user_data['order_address']}\n\n"
        "هل تؤكد الطلب؟"
    )
    kb = [
        [InlineKeyboardButton("✅ تأكيد الطلب", callback_data="confirm_order")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="home")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return ConversationHandler.END

async def confirm_order(update, context):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    cart = get_cart(context)
    total = cart_total(cart)
    with get_db() as db:
        db.execute(
            "INSERT INTO orders (user_id, username, cust_name, phone, address, items_json, total) VALUES (?,?,?,?,?,?,?)",
            (user.id, user.username or "", context.user_data.get("order_name",""),
             context.user_data.get("order_phone",""), context.user_data.get("order_address",""),
             json.dumps(cart), total)
        )
        order_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for pid, qty in cart.items():
            db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, int(pid)))
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🔔 *طلب جديد #{order_id}*\n"
                f"👤 {context.user_data.get('order_name')}\n"
                f"📱 {context.user_data.get('order_phone')}\n"
                f"📍 {context.user_data.get('order_address')}\n"
                f"💰 الإجمالي: {fmt_price(total)}",
                parse_mode="Markdown"
            )
        except: pass
    context.user_data["cart"] = {}
    await query.edit_message_text(
        f"✅ *تم تأكيد طلبك!*\n\nرقم طلبك: *#{order_id}*\nسنتواصل معك قريباً.\n\nشكراً لتسوقك معنا! 🎉",
        parse_mode="Markdown"
    )

# ══════════════════════════════════════
#  📦  طلباتي (زبون)
# ══════════════════════════════════════
async def my_orders(update, context):
    query = update.callback_query
    await query.answer()
    with get_db() as db:
        orders = db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (update.effective_user.id,)
        ).fetchall()
    if not orders:
        await query.edit_message_text("📦 لا توجد طلبات بعد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ تسوق الآن", callback_data="browse")]]))
        return
    lines = ["📦 *طلباتك الأخيرة:*\n"]
    for o in orders:
        lines.append(f"🔹 طلب #{o['id']} — {fmt_price(o['total'])}\n   {order_status_ar(o['status'])} | {o['created_at'][:10]}")
    await query.edit_message_text("\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]),
        parse_mode="Markdown")

# ══════════════════════════════════════
#  ⚙️  أدمن — المنتجات
# ══════════════════════════════════════
async def admin_products(update, context):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    with get_db() as db:
        products = db.execute("SELECT * FROM products ORDER BY id").fetchall()
    lines = ["📦 *قائمة المنتجات:*\n"]
    for p in products:
        lines.append(f"{'✅' if p['active'] else '❌'} [{p['id']}] {p['name']} — {fmt_price(p['price'])} (مخزون: {p['stock']})")
    kb = [
        [InlineKeyboardButton("➕ إضافة منتج",  callback_data="admin_add_product")],
        [InlineKeyboardButton("✏️ تعديل منتج",  callback_data="admin_edit_product")],
        [InlineKeyboardButton("🔙 رجوع",         callback_data="admin_home")],
    ]
    await query.edit_message_text("\n".join(lines) if products else "لا توجد منتجات.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_add_product_start(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["new_product"] = {}
    await query.edit_message_text("📝 اكتب *اسم المنتج*:", parse_mode="Markdown")
    return A_PROD_NAME

async def admin_add_name(update, context):
    context.user_data["new_product"]["name"] = update.message.text
    await update.message.reply_text("📝 اكتب *وصف المنتج* (أو أرسل - للتخطي):", parse_mode="Markdown")
    return A_PROD_DESC

async def admin_add_desc(update, context):
    txt = update.message.text
    context.user_data["new_product"]["description"] = "" if txt == "-" else txt
    await update.message.reply_text("💰 اكتب *السعر* (أرقام فقط):", parse_mode="Markdown")
    return A_PROD_PRICE

async def admin_add_price(update, context):
    try:
        context.user_data["new_product"]["price"] = float(update.message.text.replace(",",""))
        await update.message.reply_text("📦 اكتب *الكمية في المخزون*:", parse_mode="Markdown")
        return A_PROD_STOCK
    except ValueError:
        await update.message.reply_text("❌ أرقام فقط:")
        return A_PROD_PRICE

async def admin_add_stock(update, context):
    try:
        context.user_data["new_product"]["stock"] = int(update.message.text)
        await update.message.reply_text("🖼️ أرسل *صورة المنتج* (أو أرسل - للتخطي):", parse_mode="Markdown")
        return A_PROD_IMAGE
    except ValueError:
        await update.message.reply_text("❌ أرقام صحيحة فقط:")
        return A_PROD_STOCK

async def admin_add_image(update, context):
    np = context.user_data["new_product"]
    image_id = None
    if update.message.photo:
        image_id = update.message.photo[-1].file_id
    elif update.message.text != "-":
        await update.message.reply_text("أرسل صورة أو - للتخطي:")
        return A_PROD_IMAGE
    with get_db() as db:
        db.execute(
            "INSERT INTO products (name, description, price, stock, image_id) VALUES (?,?,?,?,?)",
            (np["name"], np.get("description",""), np["price"], np["stock"], image_id)
        )
    await update.message.reply_text(f"✅ تمت إضافة *{np['name']}* بنجاح!", parse_mode="Markdown")
    return ConversationHandler.END

async def admin_edit_product_start(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✏️ اكتب *رقم المنتج* الذي تريد تعديله:", parse_mode="Markdown")
    return A_EDIT_FIELD

async def admin_edit_select(update, context):
    try:
        pid = int(update.message.text)
        with get_db() as db:
            p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not p:
            await update.message.reply_text("❌ المنتج غير موجود:")
            return A_EDIT_FIELD
        context.user_data["edit_pid"] = pid
        kb = [
            [InlineKeyboardButton("الاسم",   callback_data="editf_name"),
             InlineKeyboardButton("الوصف",   callback_data="editf_description")],
            [InlineKeyboardButton("السعر",   callback_data="editf_price"),
             InlineKeyboardButton("المخزون", callback_data="editf_stock")],
            [InlineKeyboardButton("إيقاف/تفعيل", callback_data="editf_toggle")],
        ]
        await update.message.reply_text(f"✏️ تعديل: *{p['name']}*\nاختر الحقل:",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return A_EDIT_VALUE
    except ValueError:
        await update.message.reply_text("❌ أرقام فقط:")
        return A_EDIT_FIELD

async def admin_edit_field(update, context):
    query = update.callback_query
    await query.answer()
    field = query.data.replace("editf_","")
    pid = context.user_data["edit_pid"]
    if field == "toggle":
        with get_db() as db:
            db.execute("UPDATE products SET active = 1 - active WHERE id=?", (pid,))
        await query.edit_message_text("✅ تم تغيير حالة المنتج!")
        return ConversationHandler.END
    context.user_data["edit_field"] = field
    await query.edit_message_text(f"اكتب القيمة الجديدة لـ *{field}*:", parse_mode="Markdown")
    return A_EDIT_VALUE

async def admin_edit_value(update, context):
    field = context.user_data.get("edit_field")
    pid = context.user_data.get("edit_pid")
    value = update.message.text
    if not field or not pid:
        await update.message.reply_text("❌ حدث خطأ، حاول مرة ثانية.")
        return ConversationHandler.END
    try:
        if field == "price": value = float(value.replace(",",""))
        elif field == "stock": value = int(value)
    except ValueError:
        await update.message.reply_text("❌ قيمة غير صحيحة:")
        return A_EDIT_VALUE
    with get_db() as db:
        db.execute(f"UPDATE products SET {field}=? WHERE id=?", (value, pid))
    await update.message.reply_text(f"✅ تم تحديث *{field}* بنجاح!", parse_mode="Markdown")
    return ConversationHandler.END

# ══════════════════════════════════════
#  ⚙️  أدمن — الطلبات
# ══════════════════════════════════════
async def admin_orders(update, context):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("⏳ قيد الانتظار", callback_data="orders_pending")],
        [InlineKeyboardButton("🚚 قيد التوصيل",  callback_data="orders_shipping")],
        [InlineKeyboardButton("📦 كل الطلبات",   callback_data="orders_all")],
        [InlineKeyboardButton("🔙 رجوع",         callback_data="admin_home")],
    ]
    await query.edit_message_text("📋 *إدارة الطلبات*\nاختر الفئة:",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_list_orders(update, context):
    query = update.callback_query
    await query.answer()
    status_filter = query.data.replace("orders_","")
    with get_db() as db:
        if status_filter == "all":
            orders = db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20").fetchall()
        else:
            orders = db.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT 20", (status_filter,)).fetchall()
    if not orders:
        await query.edit_message_text("لا توجد طلبات.")
        return
    kb = [[InlineKeyboardButton(f"#{o['id']} — {o['cust_name']}", callback_data=f"order_detail_{o['id']}")] for o in orders]
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_orders")])
    lines = [f"📋 *الطلبات:*\n"] + [f"#{o['id']} | {o['cust_name']} | {fmt_price(o['total'])} | {order_status_ar(o['status'])}" for o in orders]
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_order_detail(update, context):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.split("_")[-1])
    with get_db() as db:
        o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if not o:
            await query.edit_message_text("الطلب غير موجود.")
            return
        items = json.loads(o["items_json"])
        items_lines = []
        for pid, qty in items.items():
            p = db.execute("SELECT name, price FROM products WHERE id=?", (int(pid),)).fetchone()
            if p: items_lines.append(f"  • {p['name']} × {qty} = {fmt_price(p['price'] * qty)}")
    text = (
        f"📋 *تفاصيل الطلب #{o['id']}*\n\n"
        f"👤 {o['cust_name']}\n📱 {o['phone']}\n📍 {o['address']}\n📅 {o['created_at'][:16]}\n\n"
        f"*المنتجات:*\n" + "\n".join(items_lines) +
        f"\n\n💰 *الإجمالي: {fmt_price(o['total'])}*\n📌 الحالة: {order_status_ar(o['status'])}"
    )
    statuses = ["confirmed","processing","shipping","delivered","cancelled"]
    kb = [[InlineKeyboardButton(order_status_ar(s), callback_data=f"setstatus_{oid}_{s}")] for s in statuses]
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_orders")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_set_status(update, context):
    query = update.callback_query
    await query.answer()
    _, oid, status = query.data.split("_", 2)
    with get_db() as db:
        o = db.execute("SELECT * FROM orders WHERE id=?", (int(oid),)).fetchone()
        db.execute("UPDATE orders SET status=? WHERE id=?", (status, int(oid)))
    if o:
        try:
            await context.bot.send_message(o["user_id"],
                f"🔔 *تحديث طلبك #{oid}*\n\nالحالة الجديدة: {order_status_ar(status)}",
                parse_mode="Markdown")
        except: pass
    await query.edit_message_text(f"✅ تم تحديث حالة الطلب #{oid} إلى {order_status_ar(status)}")

# ══════════════════════════════════════
#  📊  الإحصائيات (تيليغرام)
# ══════════════════════════════════════
async def admin_stats(update, context):
    query = update.callback_query
    await query.answer()
    with get_db() as db:
        total_orders  = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        total_revenue = db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='cancelled'").fetchone()[0]
        pending       = db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        delivered     = db.execute("SELECT COUNT(*) FROM orders WHERE status='delivered'").fetchone()[0]
        total_products= db.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0]
    text = (
        "📊 *إحصائيات المتجر*\n\n"
        f"📦 إجمالي الطلبات: *{total_orders}*\n"
        f"⏳ قيد الانتظار: *{pending}*\n"
        f"✅ تم التسليم: *{delivered}*\n\n"
        f"💰 إجمالي الإيرادات: *{fmt_price(total_revenue)}*\n\n"
        f"🛍️ المنتجات النشطة: *{total_products}*"
    )
    await query.edit_message_text(text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_home")]]),
        parse_mode="Markdown")

# ══════════════════════════════════════
#  🔁  التوجيه العام
# ══════════════════════════════════════
async def route_callback(update, context):
    query = update.callback_query
    data = query.data
    routing = {
        "home":             lambda: admin_main_menu(update, context) if is_admin(query.from_user.id) else customer_main_menu(update, context),
        "admin_home":       lambda: admin_main_menu(update, context),
        "browse":           lambda: browse_products(update, context),
        "view_cart":        lambda: view_cart(update, context),
        "clear_cart":       lambda: clear_cart(update, context),
        "confirm_order":    lambda: confirm_order(update, context),
        "my_orders":        lambda: my_orders(update, context),
        "admin_products":   lambda: admin_products(update, context),
        "admin_orders":     lambda: admin_orders(update, context),
        "admin_stats":      lambda: admin_stats(update, context),
        "order_detail":     lambda: admin_order_detail(update, context),
    }
    if data in routing:
        await query.answer()
        await routing[data]()
    elif data.startswith("prod_"):         await navigate_product(update, context)
    elif data.startswith("addcart_"):      await add_to_cart(update, context)
    elif data.startswith("orders_"):       await admin_list_orders(update, context)
    elif data.startswith("order_detail_"): await admin_order_detail(update, context)
    elif data.startswith("setstatus_"):    await admin_set_status(update, context)

# ══════════════════════════════════════
#  🌐  داشبورد الويب (Flask)
# ══════════════════════════════════════
web_app = Flask(__name__)

def check_auth(req):
    return req.headers.get("X-Secret") == DASHBOARD_PASS

@web_app.route("/")
def dashboard_home():
    # يرسل ملف dashboard.html مباشرة
    return send_from_directory(".", "dashboard.html")

@web_app.route("/api/products", methods=["GET"])
def api_get_products():
    if not check_auth(request): return jsonify({"error": "غير مصرح"}), 401
    with get_db() as db:
        products = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return jsonify([dict(p) for p in products])

@web_app.route("/api/products", methods=["POST"])
def api_add_product():
    if not check_auth(request): return jsonify({"error": "غير مصرح"}), 401
    data = request.json
    with get_db() as db:
        db.execute(
            "INSERT INTO products (name, description, price, stock) VALUES (?,?,?,?)",
            (data["name"], data.get("description",""), float(data["price"]), int(data["stock"]))
        )
    return jsonify({"success": True})

@web_app.route("/api/products/<int:pid>", methods=["PUT"])
def api_edit_product(pid):
    if not check_auth(request): return jsonify({"error": "غير مصرح"}), 401
    data = request.json
    with get_db() as db:
        db.execute(
            "UPDATE products SET name=?, description=?, price=?, stock=?, active=? WHERE id=?",
            (data["name"], data.get("description",""), float(data["price"]),
             int(data["stock"]), int(data.get("active",1)), pid)
        )
    return jsonify({"success": True})

@web_app.route("/api/products/<int:pid>", methods=["DELETE"])
def api_delete_product(pid):
    if not check_auth(request): return jsonify({"error": "غير مصرح"}), 401
    with get_db() as db:
        db.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
    return jsonify({"success": True})

@web_app.route("/api/orders", methods=["GET"])
def api_get_orders():
    if not check_auth(request): return jsonify({"error": "غير مصرح"}), 401
    with get_db() as db:
        orders = db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 50").fetchall()
    return jsonify([dict(o) for o in orders])

@web_app.route("/api/orders/<int:oid>", methods=["PUT"])
def api_update_order(oid):
    if not check_auth(request): return jsonify({"error": "غير مصرح"}), 401
    data = request.json
    with get_db() as db:
        db.execute("UPDATE orders SET status=? WHERE id=?", (data["status"], oid))
    return jsonify({"success": True})

@web_app.route("/api/stats", methods=["GET"])
def api_stats():
    if not check_auth(request): return jsonify({"error": "غير مصرح"}), 401
    with get_db() as db:
        total_orders  = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        total_revenue = db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='cancelled'").fetchone()[0]
        pending       = db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        products      = db.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0]
    return jsonify({
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "pending": pending,
        "products": products,
    })

# ══════════════════════════════════════
#  📱  Mini App — أوامر الأدمن
# ══════════════════════════════════════

def build_store_data() -> str:
    """يجمع كل البيانات ويحوّلها لـ base64 لإرسالها للـ Mini App"""
    import base64
    with get_db() as db:
        products = [dict(p) for p in db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()]
        orders   = [dict(o) for o in db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 30").fetchall()]
        total_orders  = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        total_revenue = db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='cancelled'").fetchone()[0]
        pending       = db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        delivered     = db.execute("SELECT COUNT(*) FROM orders WHERE status='delivered'").fetchone()[0]
        total_products= db.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0]

    data = {
        "stats": {
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "pending": pending,
            "delivered": delivered,
            "products": total_products,
        },
        "products": products,
        "orders": orders,
    }
    encoded = base64.b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()
    return encoded


async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /panel — يفتح الداشبورد للأدمن"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ غير مصرح لك")
        return

    encoded = build_store_data()
    url = f"{MINIAPP_URL}#{encoded}"

    kb = [[InlineKeyboardButton("🛒 فتح لوحة التحكم", web_app={"url": url})]]
    await update.message.reply_text(
        "📊 اضغط لفتح لوحة التحكم:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يستقبل الأوامر من الـ Mini App"""
    if not is_admin(update.effective_user.id):
        return

    try:
        data = json.loads(update.message.web_app_data.data)
        action = data.get("action")

        if action == "get_data":
            # يرسل لينك محدّث بالبيانات الجديدة
            encoded = build_store_data()
            url = f"{MINIAPP_URL}#{encoded}"
            kb = [[InlineKeyboardButton("🔄 فتح البيانات المحدّثة", web_app={"url": url})]]
            await update.message.reply_text("✅ البيانات جاهزة:", reply_markup=InlineKeyboardMarkup(kb))

        elif action == "add_product":
            with get_db() as db:
                db.execute(
                    "INSERT INTO products (name, description, price, stock) VALUES (?,?,?,?)",
                    (data["name"], data.get("desc",""), float(data["price"]), int(data["stock"]))
                )
            await update.message.reply_text(f"✅ تمت إضافة *{data['name']}* بنجاح!", parse_mode="Markdown")

        elif action == "delete_product":
            with get_db() as db:
                p = db.execute("SELECT name FROM products WHERE id=?", (data["id"],)).fetchone()
                db.execute("UPDATE products SET active=0 WHERE id=?", (data["id"],))
            name = p["name"] if p else f"#{data['id']}"
            await update.message.reply_text(f"🗑️ تم حذف *{name}*", parse_mode="Markdown")

        elif action == "toggle_product":
            with get_db() as db:
                db.execute("UPDATE products SET active = 1 - active WHERE id=?", (data["id"],))
            await update.message.reply_text(f"✅ تم تغيير حالة المنتج #{data['id']}")

        elif action == "update_order":
            oid    = data["id"]
            status = data["status"]
            with get_db() as db:
                o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
                db.execute("UPDATE orders SET status=? WHERE id=?", (status, oid))
            # إشعار الزبون
            if o:
                try:
                    await context.bot.send_message(
                        o["user_id"],
                        f"🔔 *تحديث طلبك #{oid}*\n\nالحالة: {order_status_ar(status)}",
                        parse_mode="Markdown"
                    )
                except: pass
            await update.message.reply_text(f"✅ تم تحديث الطلب #{oid} إلى {order_status_ar(status)}")

    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")


def run_web():
    web_app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

def start_dashboard():
    t = threading.Thread(target=run_web, daemon=True)
    t.start()
    print("🌐 الداشبورد يعمل على البورت 8080")

# ══════════════════════════════════════
#  🚀  تشغيل البوت
# ══════════════════════════════════════
def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    # ConversationHandler — إضافة منتج
    add_product_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_product_start, pattern="^admin_add_product$")],
        states={
            A_PROD_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_name)],
            A_PROD_DESC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_desc)],
            A_PROD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_price)],
            A_PROD_STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_stock)],
            A_PROD_IMAGE: [
                MessageHandler(filters.PHOTO, admin_add_image),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_image),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # ConversationHandler — تعديل منتج
    edit_product_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_edit_product_start, pattern="^admin_edit_product$")],
        states={
            A_EDIT_FIELD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_select),
                CallbackQueryHandler(admin_edit_field, pattern="^editf_"),
            ],
            A_EDIT_VALUE: [
                CallbackQueryHandler(admin_edit_field, pattern="^editf_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_value),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    # ConversationHandler — إتمام الطلب
    checkout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(checkout_start, pattern="^checkout$")],
        states={
            C_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_name)],
            C_PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_phone)],
            C_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_address)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("panel", panel_command))   # ← أمر فتح الداشبورد
    app.add_handler(add_product_conv)
    app.add_handler(edit_product_conv)
    app.add_handler(checkout_conv)
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(CallbackQueryHandler(route_callback))

    # ← تشغيل الداشبورد بجانب البوت
    start_dashboard()

    print("🚀 البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
