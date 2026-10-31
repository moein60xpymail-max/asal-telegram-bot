"""
Telegram bot: Asal Khanom
Python 3.10+
Install: pip install "python-telegram-bot>=21,<23"
Run:
  Linux/macOS: export BOT_TOKEN="..." ; export ADMIN_ID="123456789"
  Windows PowerShell:
    $env:BOT_TOKEN="..."
    $env:ADMIN_ID="123456789"
  python bot.py
"""

import os
import sqlite3
import random
import logging
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -------------------- Basic configuration --------------------

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
DB_PATH = "asal_bot.sqlite3"

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")
if not ADMIN_ID_RAW.isdigit():
    raise RuntimeError("ADMIN_ID must be your numeric Telegram user ID.")
ADMIN_ID = int(ADMIN_ID_RAW)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Per-user game progress and admin input mode.
# The actual editable content is stored in SQLite.
game_state: dict[tuple[int, int], str] = {}
admin_pending: dict[int, str] = {}


# -------------------- Database --------------------

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


DEFAULTS = {
    "welcome": (
        "سلام عسل خانوم! 🌷\n"
        "امیدوارم از این چیزی که براتون درست کردم کاملاً لذت ببرید.\n"
        "خیلی خری ❤️"
    ),
    "label_adventure": "🎮 شروع ماجراجویی",
    "label_gallery": "📸 گالری عکس",
    "label_messages": "💌 پیام‌ها",
    "label_surprise": "🎁 سورپرایز",
    "gallery_photo": "",
}


def init_db() -> None:
    with db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS messages "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL)"
        )
        for key, value in DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                (key, value),
            )
        count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        if count == 0:
            starter_messages = [
                "یه پیام مهم داشتم... یادم رفت چی بود!",
                "این پیام با موفقیت ارسال شد، محتوای پیام هنوز مشخص نیست.",
                "لطفاً چند لحظه صبر کنید... هیچ اتفاقی قرار نیست بیفته.",
                "طبق آخرین تحقیقات، هنوز هیچ تحقیق معتبری درباره این پیام انجام نشده!",
                "اومده بودم یه چیزی بگم، ولی دیدم همین‌طوری هم قشنگه!",
            ]
            conn.executemany(
                "INSERT INTO messages(text) VALUES(?)",
                [(m,) for m in starter_messages],
            )


def get_setting(key: str) -> str:
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else ""


def set_setting(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_messages() -> list[sqlite3.Row]:
    with db() as conn:
        return conn.execute(
            "SELECT id, text FROM messages ORDER BY id"
        ).fetchall()


def add_message(text: str) -> None:
    with db() as conn:
        conn.execute("INSERT INTO messages(text) VALUES(?)", (text,))


def delete_message(message_id: int) -> bool:
    with db() as conn:
        cur = conn.execute("DELETE FROM messages WHERE id=?", (message_id,))
        return cur.rowcount > 0


# -------------------- Keyboards and helpers --------------------

def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [get_setting("label_adventure")],
            [get_setting("label_gallery"), get_setting("label_messages")],
            [get_setting("label_surprise")],
        ],
        resize_keyboard=True,
    )


def game_key(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def game_markup(*buttons: InlineKeyboardButton) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[b] for b in buttons])


def rating_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(n), callback_data=f"rating:{n}")
         for n in range(1, 6)],
        [InlineKeyboardButton(str(n), callback_data=f"rating:{n}")
         for n in range(6, 11)],
    ])


def user_key(update: Update) -> tuple[int, int]:
    return (update.effective_chat.id, update.effective_user.id)


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    text: Optional[str] = None) -> None:
    await update.effective_message.reply_text(
        text or "از منوی زیر یکی رو انتخاب کن:",
        reply_markup=menu_keyboard(),
    )


async def send_game_message(update: Update, context: ContextTypes.DEFAULT_TYPE,
                            text: str, buttons: list[tuple[str, str]]) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=data)]
        for label, data in buttons
    ])
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def send_q1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_state[user_key(update)] = "q1"
    await send_game_message(
        update, context,
        "به نظرت معین آدم خوبیه یا نه؟",
        [("بله", "q1:yes"), ("خیر", "q1:no")],
    )


async def send_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_state[user_key(update)] = "q2"
    await send_game_message(
        update, context,
        "اگه آدم خوبیه، پس چرا انقدر دیر جوابشو می‌دی؟",
        [
            ("دوست ندارم جواب بدم.", "q2:no_interest"),
            ("سر کارم، وقت ندارم.", "q2:busy"),
            ("از این به بعد خوب جوابشو می‌دم.", "q2:promise"),
        ],
    )


async def continue_after_q2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_state[user_key(update)] = "forbidden"
    await send_game_message(
        update, context,
        "به این دکمه دست نزن!\nجدی می‌گم، اصلاً دست نزن.",
        [("🚫 دست نزن!", "forbidden:press")],
    )


async def send_twenty_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_state[user_key(update)] = "twenty"
    await send_game_message(
        update, context,
        "یه پیشنهاد برات دارم!\n"
        "از این لینک پایین می‌تونی بازی بیست‌سؤالی رو دریافت کنی و انقدر به معین با بله یا خیر جواب ندی.\n"
        "خب، تصمیمت چیه؟",
        [
            ("می‌رم دانلود کنم", "twenty:download"),
            ("فعلاً همین‌جا می‌مونم", "twenty:stay"),
        ],
    )


async def send_water(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_state[user_key(update)] = "water"
    await send_game_message(
        update, context,
        "راستی امروز آب خوردی؟",
        [("بله", "water:yes"), ("خیر", "water:no")],
    )


async def send_prize_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_state[user_key(update)] = "prize"
    await send_game_message(
        update, context,
        "یه دکمه اینجاست...",
        [("🎁 جایزه ویژه", "prize:open")],
    )


async def send_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_state[user_key(update)] = "rating"
    if update.callback_query:
        await update.callback_query.message.reply_text(
            "خب، رسیدیم به آخرین سؤال!\nاز ۱ تا ۱۰ به معین چند می‌دی؟",
            reply_markup=rating_markup(),
        )
    else:
        await update.effective_message.reply_text(
            "خب، رسیدیم به آخرین سؤال!\nاز ۱ تا ۱۰ به معین چند می‌دی؟",
            reply_markup=rating_markup(),
        )


# -------------------- User commands and menu --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    game_state.pop(user_key(update), None)
    await show_menu(update, context, get_setting("welcome"))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = (update.effective_message.text or "").strip()

    # Admin panel input is handled before normal menu selections.
    pending = admin_pending.get(user_id)
    if pending and user_id == ADMIN_ID:
        if pending == "welcome":
            set_setting("welcome", text)
            admin_pending.pop(user_id, None)
            await update.effective_message.reply_text("متن خوش‌آمدگویی ذخیره شد.")
            return
        if pending == "message":
            add_message(text)
            admin_pending.pop(user_id, None)
            await update.effective_message.reply_text("پیام جدید به فهرست اضافه شد.")
            return
        if pending == "delete_message":
            admin_pending.pop(user_id, None)
            try:
                deleted = delete_message(int(text))
            except ValueError:
                deleted = False
            await update.effective_message.reply_text(
                "پیام حذف شد." if deleted else "شماره پیام معتبر نبود."
            )
            return
        if pending == "label":
            admin_pending.pop(user_id, None)
            try:
                key, new_label = text.split("|", 1)
                key = key.strip().lower()
                new_label = new_label.strip()
                setting_key = {
                    "adventure": "label_adventure",
                    "gallery": "label_gallery",
                    "messages": "label_messages",
                    "surprise": "label_surprise",
                }.get(key)
                if not setting_key or not new_label:
                    raise ValueError
                set_setting(setting_key, new_label)
                await update.effective_message.reply_text(
                    "نام دکمه ذخیره شد. برای دیدن منوی جدید /start رو بزن."
                )
            except ValueError:
                await update.effective_message.reply_text(
                    "فرمت درست نیست. نمونه:\nadventure|🎮 شروع ماجراجویی"
                )
            return

    if text == get_setting("label_adventure"):
        await send_q1(update, context)
    elif text == get_setting("label_gallery"):
        photo_id = get_setting("gallery_photo")
        if not photo_id:
            await update.effective_message.reply_text(
                "هنوز عکسی برای گالری آپلود نشده."
            )
            return
        await update.effective_message.reply_photo(
            photo=photo_id,
            reply_markup=game_markup(game_key("بعدی", "gallery:next")),
        )
    elif text == get_setting("label_messages"):
        messages = get_messages()
        if not messages:
            await update.effective_message.reply_text("فعلاً پیامی اینجا نیست.")
            return
        chosen = random.choice(messages)
        await update.effective_message.reply_text(
            chosen["text"],
            reply_markup=game_markup(game_key("یکی دیگه", "messages:next")),
        )
    elif text == get_setting("label_surprise"):
        await update.effective_message.reply_text(
            "یه سورپرایز مخصوص برات دارم! آماده‌ای؟",
            reply_markup=game_markup(game_key("باز کردن سورپرایز", "surprise:open")),
        )


# -------------------- Game and menu callbacks --------------------

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    key = user_key(update)

    if data.startswith("admin:"):
        await admin_callbacks(update, context, data)
        return

    if data == "q1:no":
        game_state[key] = "q1"
        await query.message.reply_text(
            "خیلی خری! برگرد دوباره فکر کن.",
            reply_markup=game_markup(game_key("اوکی", "q1:again")),
        )
    elif data == "q1:again":
        await send_q1(update, context)
    elif data == "q1:yes":
        await send_q2(update, context)

    elif data == "q2:no_interest":
        game_state[key] = "q2"
        await query.message.reply_text(
            "اگه این‌جوری صحبت کنی، معین دیگه باهات حال نمی‌کنه!",
            reply_markup=game_markup(game_key("اوکی", "q2:again")),
        )
    elif data == "q2:busy":
        game_state[key] = "q2"
        await query.message.reply_text(
            "خب پس زودبه‌زود وقتتو خالی کن و جواب معین رو بده. منتظرش نذار!",
            reply_markup=game_markup(game_key("اوکی", "q2:again")),
        )
    elif data == "q2:again":
        await send_q2(update, context)
    elif data == "q2:promise":
        await query.message.reply_text("آفرین! داری دختر خوبی می‌شی. 🌷")
        await continue_after_q2(update, context)

    elif data == "forbidden:press":
        game_state[key] = "forbidden"
        await query.message.reply_text(
            "خب اسکل! دارم می‌گم دست نزن!",
            reply_markup=game_markup(game_key("اوکی", "forbidden:continue")),
        )
    elif data == "forbidden:continue":
        await send_twenty_questions(update, context)

    elif data == "twenty:download":
        game_state[key] = "twenty_download"
        await query.message.reply_text(
            "حوصله نداشتم برم برات لینک دانلود پیدا کنم. اسکل!",
            reply_markup=game_markup(game_key("اوکی", "twenty:download_ok")),
        )
    elif data == "twenty:download_ok":
        await query.message.reply_text(
            "حالا که این‌قدر اصرار داری، خودت یه فکری براش بکن.",
            reply_markup=game_markup(game_key("ادامه", "twenty:to_water")),
        )
    elif data == "twenty:stay":
        await query.message.reply_text("آفرین! داری خوب جلو می‌ری. ❤️")
        await send_water(update, context)
    elif data == "twenty:to_water":
        await send_water(update, context)

    elif data == "water:yes":
        await query.message.reply_text(
            "آفرین، منم خوردم.",
            reply_markup=game_markup(game_key("ادامه", "water:continue")),
        )
    elif data == "water:no":
        await query.message.reply_text(
            "خب برو بخور.",
            reply_markup=game_markup(game_key("ادامه", "water:continue")),
        )
    elif data == "water:continue":
        await send_prize_button(update, context)

    elif data == "prize:open":
        await query.message.reply_text(
            "فکر کردی خبریه؟",
            reply_markup=game_markup(game_key("ادامه", "prize:continue")),
        )
    elif data == "prize:continue":
        await send_rating(update, context)

    elif data.startswith("rating:"):
        try:
            score = int(data.split(":", 1)[1])
        except ValueError:
            return
        if 1 <= score <= 8:
            await query.message.reply_text(
                "معین انقدر هم ارزشش کم نیست! برو بالاتر.",
                reply_markup=rating_markup(),
            )
        elif score in (9, 10):
            await query.message.reply_text(
                "باریک‌الله! الان یه دختر خوب شدی. ازت راضیم. ❤️",
                reply_markup=game_markup(game_key("پایان مأموریت", "mission:finish")),
            )
    elif data == "mission:finish":
        game_state.pop(key, None)
        await query.message.reply_text(
            "مأموریت با موفقیت به پایان رسید!\n"
            "از این به بعد هم همین‌قدر دختر خوبی باش. ❤️",
            reply_markup=menu_keyboard(),
        )

    elif data == "gallery:next":
        await query.message.reply_text(
            "همین یکی رو تونستم با هوش مصنوعی درست کنم! "
            "بقیه‌ش یا پول می‌خواست، یا می‌گفت برو بعداً بیا. "
            "فعلاً با همین سر کن! 🌷",
            reply_markup=menu_keyboard(),
        )
    elif data == "messages:next":
        messages = get_messages()
        if messages:
            chosen = random.choice(messages)
            await query.message.reply_text(
                chosen["text"],
                reply_markup=game_markup(game_key("یکی دیگه", "messages:next")),
            )
        else:
            await query.message.reply_text(
                "فعلاً پیامی اینجا نیست.", reply_markup=menu_keyboard()
            )
    elif data == "surprise:open":
        await query.message.reply_text(
            "تبریک می‌گم! تو برنده‌ی هیچ‌چیزی نشدی. ولی حداقل تا اینجا اومدی!",
            reply_markup=menu_keyboard(),
        )


# -------------------- Admin panel --------------------

def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ویرایش پیام خوش‌آمدگویی", callback_data="admin:welcome")],
        [InlineKeyboardButton("آپلود / تغییر عکس گالری", callback_data="admin:photo")],
        [InlineKeyboardButton("حذف عکس گالری", callback_data="admin:delete_photo")],
        [InlineKeyboardButton("افزودن پیام", callback_data="admin:add_message")],
        [InlineKeyboardButton("حذف پیام", callback_data="admin:delete_message")],
        [InlineKeyboardButton("دیدن پیام‌ها", callback_data="admin:list_messages")],
        [InlineKeyboardButton("تغییر نام دکمه‌های منو", callback_data="admin:labels")],
    ])


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        await update.effective_message.reply_text("این بخش مخصوص مدیر رباته.")
        return
    await update.effective_message.reply_text(
        "پنل مدیریت ربات:\nیکی از گزینه‌ها رو انتخاب کن.",
        reply_markup=admin_keyboard(),
    )


async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          data: str) -> None:
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await query.answer("اجازه دسترسی نداری.", show_alert=True)
        return

    action = data.split(":", 1)[1]
    if action == "welcome":
        admin_pending[ADMIN_ID] = "welcome"
        await query.message.reply_text("متن خوش‌آمدگویی جدید رو در یک پیام بفرست.")
    elif action == "photo":
        admin_pending[ADMIN_ID] = "photo"
        await query.message.reply_text("حالا عکس جدید گالری رو به‌صورت عکس (Photo) بفرست.")
    elif action == "delete_photo":
        set_setting("gallery_photo", "")
        await query.message.reply_text("عکس گالری حذف شد.")
    elif action == "add_message":
        admin_pending[ADMIN_ID] = "message"
        await query.message.reply_text("متن پیام جدید رو بفرست.")
    elif action == "delete_message":
        admin_pending[ADMIN_ID] = "delete_message"
        rows = get_messages()
        if not rows:
            await query.message.reply_text("پیامی برای حذف وجود نداره.")
        else:
            listing = "\n".join(f'{r["id"]}. {r["text"]}' for r in rows)
            await query.message.reply_text(
                "شماره پیام موردنظر برای حذف رو بفرست:\n\n" + listing
            )
    elif action == "list_messages":
        rows = get_messages()
        if not rows:
            await query.message.reply_text("فعلاً پیامی ثبت نشده.")
        else:
            listing = "\n\n".join(f'{r["id"]}. {r["text"]}' for r in rows)
            await query.message.reply_text(listing)
    elif action == "labels":
        admin_pending[ADMIN_ID] = "label"
        await query.message.reply_text(
            "نام دکمه و متن جدید رو با این قالب بفرست:\n"
            "adventure|🎮 شروع ماجراجویی\n\n"
            "کلیدها:\n"
            "adventure = شروع ماجراجویی\n"
            "gallery = گالری عکس\n"
            "messages = پیام‌ها\n"
            "surprise = سورپرایز"
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id == ADMIN_ID and admin_pending.get(user_id) == "photo":
        photo_id = update.effective_message.photo[-1].file_id
        set_setting("gallery_photo", photo_id)
        admin_pending.pop(user_id, None)
        await update.effective_message.reply_text("عکس گالری ذخیره شد.")
    else:
        await update.effective_message.reply_text(
            "برای تغییر عکس گالری، از پنل مدیریت و گزینه آپلود عکس استفاده کن."
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id == ADMIN_ID:
        admin_pending.pop(ADMIN_ID, None)
        await update.effective_message.reply_text("عملیات لغو شد.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("An error occurred while handling an update:", exc_info=context.error)


def main() -> None:
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    logger.info("Bot is running.")
    app.run_polling()


if __name__ == "__main__":
    main()
