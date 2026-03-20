"""
🛒 بوت متجر تيليغرام الكامل
================================
المميزات:
  - تصفح المنتجات مع الصور
  - سلة تسوق
  - نظام طلبات مع بيانات التوصيل
  - لوحة أدمن كاملة
  - إحصائيات المبيعات

المتطلبات:
  pip install python-telegram-bot==20.3

الإعداد:
  1. غيّر TOKEN بتوكن البوت
  2. غيّر ADMIN_IDS بـ Telegram ID تبتاعك
  3. شغّل: python store_bot.py
"""

import logging
import sqlite3
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

# ─────────────────────────────────────────────
#  ⚙️  إعدادات — غيّر هذي القيم
# ─────────────────────────────────────────────
TOKEN = "8326556715:AAEt_YKn-zz_gkCD0C7V46clY9vXdGigjoU"
ADMIN_IDS = [227539181]          # ضع Telegram ID تبتاعك هنا
DB_FILE = "store.db"
CURRENCY = "IQD"                 # أو USD

# ─────────────────────────────────────────────
#  📋  حالات المحادثة
# ─────────────────────────────────────────────
(
    # أدمن — إضافة منتج
    A_PROD_NAME, A_PROD_DESC, A_PROD_PRICE,
    A_PROD_STOCK, A_PROD_IMAGE,
    # أدمن — تعديل منتج
    A_EDIT_FIELD, A_EDIT_VALUE,
    # أدمن — تحديث حالة طلب
    A_ORDER_STATUS,
    # زبون — إتمام الطلب
    C_NAME, C_PHONE, C_ADDRESS
) = range(11)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ═══════════════════════════════════════════════
#  🗄️  قاعدة البيانات
# ═══════════════════════════════════════════════

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

# ═══════════════════════════════════════════════
#  🔧  دوال مساعدة
# ═══════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def fmt_price(amount: float) -> str:
    return f"{amount:,.0f} {CURRENCY}"

def get_cart(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.setdefault("cart", {})

def cart_total(cart: dict) -> float:
    with get_db() as db:
        total = 0.0
        for pid, qty in cart.items():
            row = db.execute("SELECT price FROM products WHERE id=?", (pid,)).fetchone()
            if row:
                total += row["price"] * qty
    return total

def cart_summary(cart: dict) -> str:
    if not cart:
        return "🛒 السلة فارغة"
    lines = ["🛒 *سلتك:*\n"]
    with get_db() as db:
        for pid, qty in cart.items():
            row = db.execute("SELECT name, price FROM products WHERE id=?", (pid,)).fetchone()
            if row:
                lines.append(f"• {row['name']} × {qty} — {fmt_price(row['price'] * qty)}")
    lines.append(f"\n💰 *الإجمالي: {fmt_price(cart_total(cart))}*")
    return "\n".join(lines)

def order_status_ar(status: str) -> str:
    return {
        "pending":    "⏳ قيد الانتظار",
        "confirmed":  "✅ مؤكّد",
        "processing": "🔧 قيد التجهيز",
        "shipping":   "🚚 قيد التوصيل",
        "delivered":  "📦 تم التسليم",
        "cancelled":  "❌ ملغي",
    }.get(status, status)

# ═══════════════════════════════════════════════
#  🏠  القائمة الرئيسية
# ═══════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        await admin_main_menu(update, context)
    else:
        await customer_main_menu(update, context)

async def customer_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def admin_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# ═══════════════════════════════════════════════
#  🛍️  تصفح المنتجات (زبون)
# ═══════════════════════════════════════════════

async def browse_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    with get_db() as db:
        products = db.execute(
            "SELECT * FROM products WHERE active=1 AND stock>0 ORDER BY id"
        ).fetchall()

    if not products:
        await query.edit_message_text("😔 لا توجد منتجات متاحة حالياً.")
        return

    # عرض أول منتج
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
    if in_cart:
        text += f"\n🛒 في سلتك: {in_cart} قطعة"

    kb = []
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"prod_{index-1}"))
    if index < len(products) - 1:
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"prod_{index+1}"))
    if nav:
        kb.append(nav)

    kb.append([
        InlineKeyboardButton("➕ أضف للسلة", callback_data=f"addcart_{p['id']}"),
        InlineKeyboardButton("🛒 السلة", callback_data="view_cart"),
    ])
    kb.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])

    markup = InlineKeyboardMarkup(kb)

    # حفظ قائمة المنتجات في السياق للتنقل
    context.user_data["products_list"] = [dict(row) for row in products]

    if p["image_id"]:
        try:
            await query.message.reply_photo(
                photo=p["image_id"],
                caption=text,
                reply_markup=markup,
                parse_mode="Markdown"
            )
            await query.message.delete()
        except Exception:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")

async def navigate_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    index = int(query.data.split("_")[1])
    products_data = context.user_data.get("products_list", [])

    if not products_data:
        await query.edit_message_text("انتهت الجلسة، ابدأ من جديد.")
        return

    # تحويل القواميس إلى Row-like objects بسيطة
    class FakeRow(dict):
        def __getitem__(self, key):
            return super().__getitem__(key)

    products = [FakeRow(p) for p in products_data]
    await show_product(query, context, products, index)

# ═══════════════════════════════════════════════
#  🛒  السلة
# ═══════════════════════════════════════════════

async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ تمت الإضافة!")
    pid = query.data.split("_")[1]
    cart = get_cart(context)
    cart[pid] = cart.get(pid, 0) + 1

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🗑️ تم إفراغ السلة")
    context.user_data["cart"] = {}
    await view_cart(update, context)

# ═══════════════════════════════════════════════
#  📝  إتمام الطلب (Checkout)
# ═══════════════════════════════════════════════

async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cart = get_cart(context)
    if not cart:
        await query.edit_message_text("🛒 السلة فارغة!")
        return ConversationHandler.END

    await query.edit_message_text("📝 لإتمام طلبك، أحتاج بعض المعلومات.\n\n👤 اكتب اسمك الكامل:")
    return C_NAME

async def checkout_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order_name"] = update.message.text
    await update.message.reply_text("📱 اكتب رقم هاتفك:")
    return C_PHONE

async def checkout_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order_phone"] = update.message.text
    await update.message.reply_text("📍 اكتب عنوان التوصيل (المحافظة / المنطقة / التفاصيل):")
    return C_ADDRESS

async def checkout_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order_address"] = update.message.text
    cart = get_cart(context)
    total = cart_total(cart)

    summary = cart_summary(cart)
    text = (
        f"{summary}\n\n"
        f"👤 الاسم: {context.user_data['order_name']}\n"
        f"📱 الهاتف: {context.user_data['order_phone']}\n"
        f"📍 العنوان: {context.user_data['order_address']}\n\n"
        "هل تؤكد الطلب؟"
    )
    kb = [
        [InlineKeyboardButton("✅ تأكيد الطلب", callback_data="confirm_order")],
        [InlineKeyboardButton("❌ إلغاء",        callback_data="home")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return ConversationHandler.END

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    cart = get_cart(context)
    total = cart_total(cart)

    with get_db() as db:
        db.execute(
            """INSERT INTO orders (user_id, username, cust_name, phone, address, items_json, total)
               VALUES (?,?,?,?,?,?,?)""",
            (
                user.id,
                user.username or "",
                context.user_data.get("order_name", ""),
                context.user_data.get("order_phone", ""),
                context.user_data.get("order_address", ""),
                json.dumps(cart),
                total,
            )
        )
        order_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # تقليل المخزون
        for pid, qty in cart.items():
            db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, int(pid)))

    # إشعار الأدمن
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
        except Exception:
            pass

    context.user_data["cart"] = {}
    await query.edit_message_text(
        f"✅ *تم تأكيد طلبك!*\n\n"
        f"رقم طلبك: *#{order_id}*\n"
        f"سنتواصل معك قريباً على الرقم المقدّم.\n\n"
        f"شكراً لتسوقك معنا! 🎉",
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════
#  📦  طلباتي (زبون)
# ═══════════════════════════════════════════════

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    with get_db() as db:
        orders = db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (user.id,)
        ).fetchall()

    if not orders:
        await query.edit_message_text(
            "📦 لا توجد طلبات بعد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🛍️ تسوق الآن", callback_data="browse")
            ]])
        )
        return

    lines = ["📦 *طلباتك الأخيرة:*\n"]
    for o in orders:
        lines.append(
            f"🔹 طلب #{o['id']} — {fmt_price(o['total'])}\n"
            f"   {order_status_ar(o['status'])} | {o['created_at'][:10]}"
        )

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 الرئيسية", callback_data="home")
        ]]),
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════
#  ⚙️  لوحة الأدمن — المنتجات
# ═══════════════════════════════════════════════

async def admin_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    with get_db() as db:
        products = db.execute("SELECT * FROM products ORDER BY id").fetchall()

    lines = ["📦 *قائمة المنتجات:*\n"]
    for p in products:
        status = "✅" if p["active"] else "❌"
        lines.append(f"{status} [{p['id']}] {p['name']} — {fmt_price(p['price'])} (مخزون: {p['stock']})")

    kb = [
        [InlineKeyboardButton("➕ إضافة منتج",   callback_data="admin_add_product")],
        [InlineKeyboardButton("✏️ تعديل منتج",   callback_data="admin_edit_product")],
        [InlineKeyboardButton("🗑️ حذف منتج",    callback_data="admin_delete_product")],
        [InlineKeyboardButton("🔙 رجوع",         callback_data="admin_home")],
    ]
    await query.edit_message_text(
        "\n".join(lines) if products else "لا توجد منتجات بعد.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

# ─── إضافة منتج ───────────────────────────────

async def admin_add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_product"] = {}
    await query.edit_message_text("📝 اكتب *اسم المنتج*:", parse_mode="Markdown")
    return A_PROD_NAME

async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_product"]["name"] = update.message.text
    await update.message.reply_text("📝 اكتب *وصف المنتج* (أو أرسل - للتخطي):", parse_mode="Markdown")
    return A_PROD_DESC

async def admin_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    context.user_data["new_product"]["description"] = "" if txt == "-" else txt
    await update.message.reply_text("💰 اكتب *السعر* (أرقام فقط):", parse_mode="Markdown")
    return A_PROD_PRICE

async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", ""))
        context.user_data["new_product"]["price"] = price
        await update.message.reply_text("📦 اكتب *الكمية في المخزون*:", parse_mode="Markdown")
        return A_PROD_STOCK
    except ValueError:
        await update.message.reply_text("❌ أرقام فقط! حاول مرة ثانية:")
        return A_PROD_PRICE

async def admin_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        stock = int(update.message.text)
        context.user_data["new_product"]["stock"] = stock
        await update.message.reply_text("🖼️ أرسل *صورة المنتج* (أو أرسل - للتخطي):", parse_mode="Markdown")
        return A_PROD_IMAGE
    except ValueError:
        await update.message.reply_text("❌ أرقام صحيحة فقط:")
        return A_PROD_STOCK

async def admin_add_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            (np["name"], np.get("description", ""), np["price"], np["stock"], image_id)
        )

    await update.message.reply_text(
        f"✅ تمت إضافة *{np['name']}* بنجاح!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ─── تعديل منتج ───────────────────────────────

async def admin_edit_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✏️ اكتب *رقم المنتج* الذي تريد تعديله:", parse_mode="Markdown")
    return A_EDIT_FIELD

async def admin_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pid = int(update.message.text)
        with get_db() as db:
            p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if not p:
            await update.message.reply_text("❌ المنتج غير موجود، حاول مرة ثانية:")
            return A_EDIT_FIELD

        context.user_data["edit_pid"] = pid
        kb = [
            [InlineKeyboardButton("الاسم",   callback_data="editf_name"),
             InlineKeyboardButton("الوصف",   callback_data="editf_description")],
            [InlineKeyboardButton("السعر",   callback_data="editf_price"),
             InlineKeyboardButton("المخزون", callback_data="editf_stock")],
            [InlineKeyboardButton("إيقاف/تفعيل", callback_data="editf_toggle")],
        ]
        await update.message.reply_text(
            f"✏️ تعديل: *{p['name']}*\nاختر الحقل:", 
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
        return A_EDIT_VALUE
    except ValueError:
        await update.message.reply_text("❌ أرقام فقط:")
        return A_EDIT_FIELD

async def admin_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.replace("editf_", "")
    pid = context.user_data["edit_pid"]

    if field == "toggle":
        with get_db() as db:
            db.execute("UPDATE products SET active = 1 - active WHERE id=?", (pid,))
        await query.edit_message_text("✅ تم تغيير حالة المنتج!")
        return ConversationHandler.END

    context.user_data["edit_field"] = field
    await query.edit_message_text(f"اكتب القيمة الجديدة لـ *{field}*:", parse_mode="Markdown")
    return A_EDIT_VALUE

async def admin_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data.get("edit_field")
    pid = context.user_data.get("edit_pid")
    value = update.message.text

    if not field or not pid:
        await update.message.reply_text("❌ حدث خطأ، حاول مرة ثانية من البداية.")
        return ConversationHandler.END

    try:
        if field == "price":
            value = float(value.replace(",", ""))
        elif field == "stock":
            value = int(value)
    except ValueError:
        await update.message.reply_text("❌ قيمة غير صحيحة:")
        return A_EDIT_VALUE

    with get_db() as db:
        db.execute(f"UPDATE products SET {field}=? WHERE id=?", (value, pid))

    await update.message.reply_text(f"✅ تم تحديث *{field}* بنجاح!", parse_mode="Markdown")
    return ConversationHandler.END

# ─── حذف منتج ─────────────────────────────────

async def admin_delete_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🗑️ اكتب *رقم المنتج* الذي تريد حذفه:", parse_mode="Markdown")

async def handle_delete_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get("awaiting_delete"):
        return
    try:
        pid = int(update.message.text)
        with get_db() as db:
            p = db.execute("SELECT name FROM products WHERE id=?", (pid,)).fetchone()
            if p:
                db.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
                await update.message.reply_text(f"✅ تم حذف *{p['name']}*", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ المنتج غير موجود")
        context.user_data["awaiting_delete"] = False
    except ValueError:
        await update.message.reply_text("❌ أرقام فقط")

# ═══════════════════════════════════════════════
#  ⚙️  لوحة الأدمن — الطلبات
# ═══════════════════════════════════════════════

async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    kb = [
        [InlineKeyboardButton("⏳ قيد الانتظار",   callback_data="orders_pending")],
        [InlineKeyboardButton("✅ المؤكدة",         callback_data="orders_confirmed")],
        [InlineKeyboardButton("🚚 قيد التوصيل",    callback_data="orders_shipping")],
        [InlineKeyboardButton("📦 كل الطلبات",     callback_data="orders_all")],
        [InlineKeyboardButton("🔙 رجوع",           callback_data="admin_home")],
    ]
    await query.edit_message_text(
        "📋 *إدارة الطلبات*\nاختر الفئة:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def admin_list_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    status_filter = query.data.replace("orders_", "")

    with get_db() as db:
        if status_filter == "all":
            orders = db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 20").fetchall()
        else:
            orders = db.execute(
                "SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT 20",
                (status_filter,)
            ).fetchall()

    if not orders:
        await query.edit_message_text("لا توجد طلبات.")
        return

    lines = [f"📋 *الطلبات ({status_filter}):*\n"]
    for o in orders:
        lines.append(
            f"#{o['id']} | {o['cust_name']} | {fmt_price(o['total'])} | {order_status_ar(o['status'])}"
        )

    kb = []
    for o in orders:
        kb.append([InlineKeyboardButton(
            f"#{o['id']} — {o['cust_name']}",
            callback_data=f"order_detail_{o['id']}"
        )])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_orders")])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def admin_order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    oid = int(query.data.split("_")[-1])

    with get_db() as db:
        o = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if not o:
            await query.edit_message_text("الطلب غير موجود.")
            return

        # قراءة تفاصيل المنتجات
        items = json.loads(o["items_json"])
        items_lines = []
        for pid, qty in items.items():
            p = db.execute("SELECT name, price FROM products WHERE id=?", (int(pid),)).fetchone()
            if p:
                items_lines.append(f"  • {p['name']} × {qty} = {fmt_price(p['price'] * qty)}")

    text = (
        f"📋 *تفاصيل الطلب #{o['id']}*\n\n"
        f"👤 {o['cust_name']}\n"
        f"📱 {o['phone']}\n"
        f"📍 {o['address']}\n"
        f"📅 {o['created_at'][:16]}\n\n"
        f"*المنتجات:*\n" + "\n".join(items_lines) + "\n\n"
        f"💰 *الإجمالي: {fmt_price(o['total'])}*\n"
        f"📌 الحالة: {order_status_ar(o['status'])}"
    )

    statuses = ["confirmed", "processing", "shipping", "delivered", "cancelled"]
    kb = [[InlineKeyboardButton(order_status_ar(s), callback_data=f"setstatus_{oid}_{s}")] for s in statuses]
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_orders")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_set_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, oid, status = query.data.split("_", 2)

    with get_db() as db:
        o = db.execute("SELECT * FROM orders WHERE id=?", (int(oid),)).fetchone()
        db.execute("UPDATE orders SET status=? WHERE id=?", (status, int(oid)))

    # إشعار الزبون
    if o:
        try:
            await context.bot.send_message(
                o["user_id"],
                f"🔔 *تحديث طلبك #{oid}*\n\nالحالة الجديدة: {order_status_ar(status)}",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    await query.edit_message_text(f"✅ تم تحديث حالة الطلب #{oid} إلى {order_status_ar(status)}")

# ═══════════════════════════════════════════════
#  📊  الإحصائيات
# ═══════════════════════════════════════════════

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    with get_db() as db:
        total_orders   = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        total_revenue  = db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status != 'cancelled'").fetchone()[0]
        pending        = db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        delivered      = db.execute("SELECT COUNT(*) FROM orders WHERE status='delivered'").fetchone()[0]
        total_products = db.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0]
        low_stock      = db.execute("SELECT COUNT(*) FROM products WHERE stock <= 3 AND active=1").fetchone()[0]

        # أكثر المنتجات مبيعاً
        orders_data = db.execute("SELECT items_json FROM orders WHERE status != 'cancelled'").fetchall()
        sales_count = {}
        for row in orders_data:
            try:
                items = json.loads(row["items_json"])
                for pid, qty in items.items():
                    sales_count[pid] = sales_count.get(pid, 0) + qty
            except Exception:
                pass

        top_products = []
        for pid, qty in sorted(sales_count.items(), key=lambda x: -x[1])[:3]:
            p = db.execute("SELECT name FROM products WHERE id=?", (int(pid),)).fetchone()
            if p:
                top_products.append(f"  🥇 {p['name']} — {qty} مبيعة")

    text = (
        "📊 *إحصائيات المتجر*\n\n"
        f"📦 إجمالي الطلبات: *{total_orders}*\n"
        f"⏳ قيد الانتظار: *{pending}*\n"
        f"✅ تم التسليم: *{delivered}*\n\n"
        f"💰 إجمالي الإيرادات: *{fmt_price(total_revenue)}*\n\n"
        f"🛍️ المنتجات النشطة: *{total_products}*\n"
        f"⚠️ مخزون منخفض: *{low_stock}*\n\n"
    )

    if top_products:
        text += "*🏆 أكثر المنتجات مبيعاً:*\n" + "\n".join(top_products)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data="admin_home")
        ]]),
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════
#  🔁  التوجيه العام
# ═══════════════════════════════════════════════

async def route_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "home":
        await query.answer()
        if is_admin(query.from_user.id):
            await admin_main_menu(update, context)
        else:
            await customer_main_menu(update, context)
    elif data == "admin_home":
        await query.answer()
        await admin_main_menu(update, context)
    elif data == "browse":
        await browse_products(update, context)
    elif data == "view_cart":
        await view_cart(update, context)
    elif data == "clear_cart":
        await clear_cart(update, context)
    elif data == "checkout":
        return await checkout_start(update, context)
    elif data == "confirm_order":
        await confirm_order(update, context)
    elif data == "my_orders":
        await my_orders(update, context)
    elif data == "admin_products":
        await admin_products(update, context)
    elif data == "admin_orders":
        await admin_orders(update, context)
    elif data == "admin_stats":
        await admin_stats(update, context)
    elif data.startswith("prod_"):
        await navigate_product(update, context)
    elif data.startswith("addcart_"):
        await add_to_cart(update, context)
    elif data.startswith("orders_"):
        await admin_list_orders(update, context)
    elif data.startswith("order_detail_"):
        await admin_order_detail(update, context)
    elif data.startswith("setstatus_"):
        await admin_set_status(update, context)
    elif data == "admin_delete_product":
        await admin_delete_product(update, context)
        context.user_data["awaiting_delete"] = True

# ═══════════════════════════════════════════════
#  🚀  تشغيل البوت
# ═══════════════════════════════════════════════

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
    app.add_handler(add_product_conv)
    app.add_handler(edit_product_conv)
    app.add_handler(checkout_conv)
    app.add_handler(CallbackQueryHandler(route_callback))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_delete_id
    ))

    print("🚀 البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
