
import asyncio
import logging
import re
import sqlite3
import json
import random
import string
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from threading import Thread

from flask import Flask, request, jsonify
import requests
import nest_asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions,
    ChatMemberAdministrator, ChatMemberOwner, ChatMemberMember,
    InputMediaPhoto, InputFile
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, CallbackContext
)
from telegram.constants import ParseMode

# ==================== التهيئة ====================
nest_asyncio.apply()

app_flask = Flask(__name__)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = "8700746570:AAEDSxqlAVJlijQL_feqdh0LsUhY91pzpcY"
ADMIN_ID = 7093004518
BOT_USERNAME = "sudaniTechsbitesbot"
WELCOME_IMAGE = "https://files.catbox.moe/c8sskq.jpg"
FORCE_CHANNEL = "@YourChannel"
FORCE_CHAT_ID = -1001234567890
DEVELOPER_CHAT_ID = -1001234567891
CAPTCHA_TIMEOUT = 60

# ==================== قاعدة البيانات ====================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect("group_protection.db", check_same_thread=False)
        self.cur = self.conn.cursor()
        self._init_tables()
        self._migrate_tables()
    
    def _migrate_tables(self):
        try:
            self.cur.execute("PRAGMA table_info(active_users)")
            columns = [col[1] for col in self.cur.fetchall()]
            if "last_active" not in columns:
                self.cur.execute("ALTER TABLE active_users ADD COLUMN last_active TEXT DEFAULT '1970-01-01T00:00:00'")
                self.conn.commit()
        except Exception as e:
            logging.warning(f"Migration warning: {e}")
    
    def _init_tables(self):
        self.cur.execute("""CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            antilink INTEGER DEFAULT 1,
            antibadword INTEGER DEFAULT 1,
            antispam INTEGER DEFAULT 1,
            antiphoto INTEGER DEFAULT 0,
            antisticker INTEGER DEFAULT 0,
            antivideo INTEGER DEFAULT 0,
            antireply INTEGER DEFAULT 0,
            antibot INTEGER DEFAULT 1,
            antiurl INTEGER DEFAULT 1,
            badwords TEXT DEFAULT 'كس,خا,زق,حرام,شرموطة,عاهرة,قحبة,منيوك,نايك,لوطي,مثلي,زب,كوس',
            punish_type TEXT DEFAULT 'mute',
            mute_minutes INTEGER DEFAULT 60,
            welcome_enabled INTEGER DEFAULT 1,
            welcome_text TEXT DEFAULT '',
            force_subscribe INTEGER DEFAULT 0,
            security_mode INTEGER DEFAULT 0,
            log_channel INTEGER DEFAULT 0,
            captcha_enabled INTEGER DEFAULT 0,
            auto_delete INTEGER DEFAULT 0,
            delete_seconds INTEGER DEFAULT 60,
            welcome_photo TEXT DEFAULT ''
        )""")
        
        self.cur.execute("""CREATE TABLE IF NOT EXISTS bot_groups (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT,
            added_at TEXT,
            admin_id INTEGER DEFAULT 0
        )""")
        
        self.cur.execute("""CREATE TABLE IF NOT EXISTS user_spam (
            chat_id INTEGER,
            user_id INTEGER,
            timestamps TEXT,
            warns INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id)
        )""")
        
        self.cur.execute("""CREATE TABLE IF NOT EXISTS active_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_active TEXT
        )""")
        
        self.cur.execute("""CREATE TABLE IF NOT EXISTS global_bans (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            banned_by INTEGER,
            banned_at TEXT
        )""")
        
        self.cur.execute("""CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            reporter_id INTEGER,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )""")
        
        self.cur.execute("""CREATE TABLE IF NOT EXISTS captcha_cache (
            chat_id INTEGER,
            user_id INTEGER,
            code TEXT,
            created_at TEXT,
            PRIMARY KEY(chat_id, user_id)
        )""")
        
        self.cur.execute("""CREATE TABLE IF NOT EXISTS auto_delete_cache (
            chat_id INTEGER,
            message_id INTEGER,
            user_id INTEGER,
            delete_at TEXT,
            PRIMARY KEY(chat_id, message_id)
        )""")
        
        self.cur.execute("""CREATE TABLE IF NOT EXISTS user_private_welcome (
            user_id INTEGER PRIMARY KEY,
            photo_url TEXT,
            updated_at TEXT
        )""")
        
        self.conn.commit()
    
    def get_settings(self, chat_id: int) -> Dict:
        self.cur.execute("SELECT * FROM group_settings WHERE chat_id=?", (chat_id,))
        row = self.cur.fetchone()
        if not row:
            self.cur.execute("INSERT INTO group_settings(chat_id) VALUES(?)", (chat_id,))
            self.conn.commit()
            return self.get_settings(chat_id)
        
        columns = ["chat_id", "antilink", "antibadword", "antispam", "antiphoto",
                  "antisticker", "antivideo", "antireply", "antibot", "antiurl",
                  "badwords", "punish_type", "mute_minutes", "welcome_enabled",
                  "welcome_text", "force_subscribe", "security_mode", "log_channel",
                  "captcha_enabled", "auto_delete", "delete_seconds", "welcome_photo"]
        
        result = {}
        for i, col in enumerate(columns):
            if i < len(row):
                if col == "badwords":
                    result[col] = row[i].split(",") if row[i] else []
                else:
                    result[col] = row[i]
        return result
    
    def update_setting(self, chat_id: int, key: str, value):
        try:
            self.cur.execute(f"UPDATE group_settings SET {key}=? WHERE chat_id=?", (value, chat_id))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Update setting error: {e}")
    
    def add_group(self, chat_id: int, chat_title: str, admin_id: int = None):
        self.cur.execute(
            "INSERT OR REPLACE INTO bot_groups(chat_id, chat_title, added_at, admin_id) VALUES(?,?,?,?)",
            (chat_id, chat_title, datetime.now().strftime("%Y-%m-%d %H:%M"), admin_id or 0)
        )
        self.conn.commit()
    
    def get_user_groups(self, user_id: int) -> List[Dict]:
        if user_id == ADMIN_ID:
            self.cur.execute("SELECT chat_id, chat_title FROM bot_groups ORDER BY chat_title")
        else:
            self.cur.execute("SELECT chat_id, chat_title FROM bot_groups WHERE admin_id=? ORDER BY chat_title", (user_id,))
        return [{"id": row[0], "title": row[1]} for row in self.cur.fetchall() if row[0] < 0]
    
    def add_active_user(self, user_id: int, username: str, first_name: str):
        self.cur.execute(
            "INSERT OR REPLACE INTO active_users(user_id, username, first_name, last_active) VALUES(?,?,?,?)",
            (user_id, username or "NoUsername", first_name or "User", datetime.now().isoformat())
        )
        self.conn.commit()
    
    def get_all_users(self) -> List[int]:
        self.cur.execute("SELECT user_id FROM active_users")
        return [row[0] for row in self.cur.fetchall()]
    
    def add_spam(self, chat_id: int, user_id: int) -> Tuple[bool, int]:
        now = datetime.now().timestamp()
        self.cur.execute("SELECT timestamps, warns FROM user_spam WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = self.cur.fetchone()
        
        times = []
        warns = 0
        if row and row[0]:
            times = [float(t) for t in row[0].split(",") if t]
            warns = row[1] or 0
        
        times = [t for t in times if now - t < 10]
        times.append(now)
        
        is_spam = len(times) > 5
        if is_spam:
            warns += 1
        
        self.cur.execute(
            "INSERT OR REPLACE INTO user_spam(chat_id, user_id, timestamps, warns) VALUES(?,?,?,?)",
            (chat_id, user_id, ",".join(map(str, times)), warns)
        )
        self.conn.commit()
        return is_spam, warns
    
    def reset_spam(self, chat_id: int, user_id: int):
        self.cur.execute("DELETE FROM user_spam WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        self.conn.commit()
    
    def add_global_ban(self, user_id: int, reason: str, banned_by: int):
        self.cur.execute(
            "INSERT OR REPLACE INTO global_bans(user_id, reason, banned_by, banned_at) VALUES(?,?,?,?)",
            (user_id, reason, banned_by, datetime.now().isoformat())
        )
        self.conn.commit()
    
    def is_globally_banned(self, user_id: int) -> bool:
        self.cur.execute("SELECT user_id FROM global_bans WHERE user_id=?", (user_id,))
        return self.cur.fetchone() is not None
    
    def add_report(self, chat_id: int, user_id: int, reporter_id: int, reason: str):
        self.cur.execute(
            "INSERT INTO reports(chat_id, user_id, reporter_id, reason, created_at) VALUES(?,?,?,?,?)",
            (chat_id, user_id, reporter_id, reason, datetime.now().isoformat())
        )
        self.conn.commit()
        return self.cur.lastrowid
    
    def save_captcha(self, chat_id: int, user_id: int, code: str):
        self.cur.execute(
            "INSERT OR REPLACE INTO captcha_cache(chat_id, user_id, code, created_at) VALUES(?,?,?,?)",
            (chat_id, user_id, code, datetime.now().isoformat())
        )
        self.conn.commit()
    
    def get_captcha(self, chat_id: int, user_id: int) -> Optional[str]:
        self.cur.execute("SELECT code, created_at FROM captcha_cache WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = self.cur.fetchone()
        if not row:
            return None
        
        created = datetime.fromisoformat(row[1])
        if (datetime.now() - created).seconds > CAPTCHA_TIMEOUT:
            self.cur.execute("DELETE FROM captcha_cache WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            self.conn.commit()
            return None
        
        return row[0]
    
    def delete_captcha(self, chat_id: int, user_id: int):
        self.cur.execute("DELETE FROM captcha_cache WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        self.conn.commit()
    
    def add_auto_delete(self, chat_id: int, message_id: int, user_id: int, seconds: int):
        delete_at = (datetime.now() + timedelta(seconds=seconds)).isoformat()
        self.cur.execute(
            "INSERT OR REPLACE INTO auto_delete_cache(chat_id, message_id, user_id, delete_at) VALUES(?,?,?,?)",
            (chat_id, message_id, user_id, delete_at)
        )
        self.conn.commit()
    
    def get_auto_delete_messages(self) -> List[Tuple[int, int, int]]:
        now = datetime.now().isoformat()
        self.cur.execute(
            "SELECT chat_id, message_id, user_id FROM auto_delete_cache WHERE delete_at <= ?",
            (now,)
        )
        return self.cur.fetchall()
    
    def remove_auto_delete(self, chat_id: int, message_id: int):
        self.cur.execute("DELETE FROM auto_delete_cache WHERE chat_id=? AND message_id=?", (chat_id, message_id))
        self.conn.commit()
    
    def get_private_welcome(self, user_id: int) -> Optional[str]:
        self.cur.execute("SELECT photo_url FROM user_private_welcome WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return row[0] if row else None
    
    def set_private_welcome(self, user_id: int, photo_url: str):
        self.cur.execute(
            "INSERT OR REPLACE INTO user_private_welcome(user_id, photo_url, updated_at) VALUES(?,?,?)",
            (user_id, photo_url, datetime.now().isoformat())
        )
        self.conn.commit()

db = Database()

# ==================== دوال المساعدة ====================
async def is_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False

async def is_bot_admin(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        bot = await context.bot.get_chat_member(chat_id, context.bot.id)
        return isinstance(bot, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False

async def generate_captcha() -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ==================== لوحات المفاتيح ====================
def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ أضفني لمجموعة", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")],
        [InlineKeyboardButton("📋 مجموعاتي", callback_data="my_groups")],
        [InlineKeyboardButton("🛡️ لوحة الحماية", callback_data="panel")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="stats_user")],
        [InlineKeyboardButton("❓ المساعدة", callback_data="help")]
    ])

def admin_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إذاعة للمستخدمين", callback_data="broadcast_all"),
         InlineKeyboardButton("📢 إذاعة للمجموعات", callback_data="broadcast_groups")],
        [InlineKeyboardButton("📊 إحصائيات البوت", callback_data="stats_admin"),
         InlineKeyboardButton("🚫 الحظر العالمي", callback_data="global_ban")],
        [InlineKeyboardButton("📋 التقارير", callback_data="reports_list")],
        [InlineKeyboardButton("👤 لوحة المستخدمين", callback_data="user_panel")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])

def panel_keyboard(chat_id: int):
    s = db.get_settings(chat_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅' if s.get('antilink',1) else '❌'} مضاد الروابط", callback_data="toggle_antilink"),
         InlineKeyboardButton(f"{'✅' if s.get('antibadword',1) else '❌'} مضاد الكلمات", callback_data="toggle_antibad")],
        [InlineKeyboardButton(f"{'✅' if s.get('antispam',1) else '❌'} مضاد السبام", callback_data="toggle_antispam"),
         InlineKeyboardButton(f"{'✅' if s.get('antireply',0) else '❌'} منع الردود", callback_data="toggle_antireply")],
        [InlineKeyboardButton(f"{'✅' if s.get('antibot',1) else '❌'} منع البوتات", callback_data="toggle_antibot"),
         InlineKeyboardButton(f"{'✅' if s.get('antiurl',1) else '❌'} منع الروابط المختصرة", callback_data="toggle_antiurl")],
        [InlineKeyboardButton(f"{'✅' if s.get('antiphoto',0) else '❌'} منع الصور", callback_data="toggle_antiphoto"),
         InlineKeyboardButton(f"{'✅' if s.get('antisticker',0) else '❌'} منع الملصقات", callback_data="toggle_antisticker")],
        [InlineKeyboardButton(f"{'✅' if s.get('antivideo',0) else '❌'} منع الفيديو", callback_data="toggle_antivideo"),
         InlineKeyboardButton(f"{'✅' if s.get('welcome_enabled',1) else '❌'} الترحيب", callback_data="toggle_welcome")],
        [InlineKeyboardButton(f"{'✅' if s.get('force_subscribe',0) else '❌'} اشتراك إجباري", callback_data="toggle_force"),
         InlineKeyboardButton(f"{'✅' if s.get('captcha_enabled',0) else '❌'} كابتشا", callback_data="toggle_captcha")],
        [InlineKeyboardButton(f"🛡️ {'ON' if s.get('security_mode',0) else 'OFF'} الوضع الأمني", callback_data="toggle_security"),
         InlineKeyboardButton(f"⏱️ {'ON' if s.get('auto_delete',0) else 'OFF'} حذف تلقائي", callback_data="toggle_auto_delete")],
        [InlineKeyboardButton("📝 تعديل الكلمات", callback_data="edit_badwords"),
         InlineKeyboardButton("⚖️ نوع العقوبة", callback_data="set_punishment")],
        [InlineKeyboardButton("⏱️ مدة الكتم", callback_data="set_mute_time"),
         InlineKeyboardButton("⏱️ مدة الحذف", callback_data="set_delete_time")],
        [InlineKeyboardButton("📸 تغيير صورة الترحيب", callback_data="change_welcome_photo")],
        [InlineKeyboardButton("🔄 إعادة ضبط", callback_data="reset_settings")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ])

def groups_keyboard(groups: List[Dict], page: int = 0):
    buttons = []
    per_page = 8
    start = page * per_page
    end = start + per_page
    
    for group in groups[start:end]:
        buttons.append([InlineKeyboardButton(f"📌 {group['title'][:25]}", callback_data=f"group_{group['id']}")])
    
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"groups_page_{page-1}"))
    if end < len(groups):
        nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"groups_page_{page+1}"))
    if nav:
        buttons.append(nav)
    
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def punishment_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 حظر", callback_data="punish_ban"),
         InlineKeyboardButton("🔇 كتم", callback_data="punish_mute"),
         InlineKeyboardButton("⚠️ طرد", callback_data="punish_kick")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="panel")]
    ])

def mute_time_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5 دقائق", callback_data="mute_5"),
         InlineKeyboardButton("30 دقيقة", callback_data="mute_30"),
         InlineKeyboardButton("1 ساعة", callback_data="mute_60")],
        [InlineKeyboardButton("6 ساعات", callback_data="mute_360"),
         InlineKeyboardButton("1 يوم", callback_data="mute_1440"),
         InlineKeyboardButton("3 أيام", callback_data="mute_4320")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="set_punishment")]
    ])

def delete_time_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("10 ثواني", callback_data="delete_10"),
         InlineKeyboardButton("30 ثانية", callback_data="delete_30"),
         InlineKeyboardButton("1 دقيقة", callback_data="delete_60")],
        [InlineKeyboardButton("5 دقائق", callback_data="delete_300"),
         InlineKeyboardButton("10 دقائق", callback_data="delete_600"),
         InlineKeyboardButton("30 دقيقة", callback_data="delete_1800")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="panel")]
    ])

# ==================== أزرار الصور ====================
def welcome_photo_keyboard(chat_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 تغيير الصورة", callback_data=f"change_welcome_photo_{chat_id}")],
        [InlineKeyboardButton("🔄 إعادة تعيين", callback_data=f"reset_welcome_photo_{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="panel")]
    ])

# ==================== الأوامر الرئيسية ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_active_user(user.id, user.username, user.first_name)
    
    if update.effective_chat.type == "private":
        private_photo = db.get_private_welcome(user.id)
        photo_to_use = private_photo or WELCOME_IMAGE
        
        try:
            if user.id == ADMIN_ID:
                await context.bot.send_photo(
                    chat_id=user.id,
                    photo=photo_to_use,
                    caption="🌟 **مرحباً أيها المطور** 🌟\n\n🔧 تحكم كامل بالبوت.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=admin_panel_keyboard()
                )
            else:
                await context.bot.send_photo(
                    chat_id=user.id,
                    photo=photo_to_use,
                    caption=f"🌟 **أهلاً بك في بوت الحماية المتطور** 🌟\n\n👤 **الاسم:** {user.full_name}\n🆔 **المعرف:** `{user.id}`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=main_keyboard()
                )
        except Exception as e:
            logging.error(f"Start photo error: {e}")
            # Fallback to text if photo fails
            if user.id == ADMIN_ID:
                await update.message.reply_text(
                    "🌟 مرحباً أيها المطور 🌟\n🔧 تحكم كامل بالبوت.",
                    reply_markup=admin_panel_keyboard()
                )
            else:
                await update.message.reply_text(
                    f"🌟 أهلاً بك في بوت الحماية المتطور 🌟\n\n👤 الاسم: {user.full_name}",
                    reply_markup=main_keyboard()
                )
    else:
        db.add_group(update.effective_chat.id, update.effective_chat.title)
        await update.message.reply_text("✅ تم تفعيل البوت في هذه المجموعة!")

async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if chat_id > 0:
        await update.message.reply_text(
            "⚠️ هذا الأمر يعمل داخل المجموعات فقط.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 مجموعاتي", callback_data="my_groups")]
            ])
        )
        return
    
    if not await is_admin(chat_id, user_id, context):
        await update.message.reply_text("⛔ للمشرفين فقط.")
        return
    
    if not await is_bot_admin(chat_id, context):
        await update.message.reply_text("❌ البوت ليس مشرفاً في هذه المجموعة.")
        return
    
    chat = await context.bot.get_chat(chat_id)
    await update.message.reply_text(
        f"🛡️ **لوحة حماية: {chat.title}**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=panel_keyboard(chat_id)
    )

# ==================== أوامر الصور ====================
async def set_group_welcome_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if chat_id > 0:
        await update.message.reply_text("⚠️ هذا الأمر يعمل داخل المجموعات فقط.")
        return
    
    if not await is_admin(chat_id, user_id, context):
        await update.message.reply_text("⛔ للمشرفين فقط.")
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text(
            "📸 **طريقة الاستخدام:**\n"
            "أرسل الصورة التي تريدها، ثم رد على الصورة بـ:\n"
            "`/setwelcomephoto`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    photo = update.message.reply_to_message.photo[-1]
    file_id = photo.file_id
    
    db.update_setting(chat_id, "welcome_photo", file_id)
    
    await update.message.reply_text(
        "✅ **تم تغيير صورة الترحيب بنجاح!**",
        parse_mode=ParseMode.MARKDOWN
    )

async def set_private_welcome_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if update.effective_chat.type != "private":
        await update.message.reply_text("⚠️ هذا الأمر يعمل في الخاص فقط.")
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text(
            "📸 **طريقة الاستخدام:**\n"
            "أرسل الصورة التي تريدها، ثم رد على الصورة بـ:\n"
            "`/setprivatephoto`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    photo = update.message.reply_to_message.photo[-1]
    file_id = photo.file_id
    
    db.set_private_welcome(user_id, file_id)
    
    await update.message.reply_text(
        "✅ **تم تغيير صورة الترحيب الخاصة بنجاح!**",
        parse_mode=ParseMode.MARKDOWN
    )

async def reset_welcome_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if chat_id > 0:
        await update.message.reply_text("⚠️ هذا الأمر يعمل داخل المجموعات فقط.")
        return
    
    if not await is_admin(chat_id, user_id, context):
        await update.message.reply_text("⛔ للمشرفين فقط.")
        return
    
    db.update_setting(chat_id, "welcome_photo", "")
    await update.message.reply_text(
        "✅ **تم إعادة تعيين صورة الترحيب إلى الصورة الافتراضية.**",
        parse_mode=ParseMode.MARKDOWN
    )

async def my_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    groups = db.get_user_groups(user_id)
    
    if not groups:
        await query.edit_message_text(
            "📋 لم يتم العثور على مجموعات.\nأضف البوت لمجموعة واجعله مشرف أولاً.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ])
        )
        return
    
    await query.edit_message_text(
        f"📋 **مجموعاتك:** {len(groups)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=groups_keyboard(groups, 0)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📖 **دليل استخدام البوت**\n\n"
        f"🔹 **الأوامر الأساسية:**\n"
        f"/start - بدء البوت\n"
        f"/panel - لوحة التحكم\n"
        f"/mute @user - كتم عضو\n"
        f"/unmute @user - فك الكتم\n"
        f"/ban @user - حظر عضو\n"
        f"/kick @user - طرد عضو\n"
        f"/report @user سبب - إبلاغ عن عضو\n"
        f"/stats - إحصائيات المجموعة\n\n"
        f"📸 **أوامر الصور:**\n"
        f"/setwelcomephoto - تغيير صورة ترحيب المجموعة\n"
        f"/setprivatephoto - تغيير صورة ترحيب الخاص\n"
        f"/resetwelcomephoto - إعادة تعيين صورة الترحيب",
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== معالجة الرسائل ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text
    
    if text.startswith("/"):
        return
    
    if db.is_globally_banned(user_id):
        await context.bot.ban_chat_member(chat_id, user_id)
        await update.message.reply_text("🚫 تم حظرك بواسطة الحماية العالمية.")
        return
    
    if await is_admin(chat_id, user_id, context):
        return
    
    settings = db.get_settings(chat_id)
    
    if settings.get("captcha_enabled", 0):
        captcha_code = db.get_captcha(chat_id, user_id)
        if captcha_code:
            if text.strip() == captcha_code:
                db.delete_captcha(chat_id, user_id)
                await update.message.reply_text("✅ تم التحقق بنجاح! مرحباً بك في المجموعة.")
                return
            else:
                await update.message.delete()
                await update.message.reply_text(
                    "❌ رمز الكابتشا غير صحيح.\n"
                    f"📝 أرسل الرمز المطلوب: `{captcha_code}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
    
    if settings.get("security_mode", 0):
        await apply_punishment(update, context, "وضع أمني فائق")
        return
    
    if settings.get("antilink", 1):
        link_patterns = [
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+])+',
            r't\.me/[a-zA-Z0-9_]+',
            r'telegram\.me/[a-zA-Z0-9_]+',
            r'www\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}'
        ]
        for pattern in link_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                await apply_punishment(update, context, "إرسال رابط")
                return
    
    if settings.get("antiurl", 1):
        short_urls = ['bit.ly', 'tinyurl', 'shorturl', 'goo.gl', 'ow.ly', 'is.gd']
        if any(url in text.lower() for url in short_urls):
            await apply_punishment(update, context, "رابط مختصر محظور")
            return
    
    if settings.get("antibadword", 1):
        badwords = settings.get("badwords", [])
        for word in badwords:
            if word and word.lower() in text.lower():
                await apply_punishment(update, context, f"كلمة سيئة: {word}")
                return
    
    if settings.get("antispam", 1):
        is_spam, warns = db.add_spam(chat_id, user_id)
        if is_spam:
            await apply_punishment(update, context, f"سبام - تحذير {warns}")
            return

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if await is_admin(chat_id, user_id, context):
        return
    
    settings = db.get_settings(chat_id)
    
    if settings.get("security_mode", 0):
        await apply_punishment(update, context, "وضع أمني - منع الميديا")
        return
    
    if settings.get("antiphoto", 0) and update.message.photo:
        await apply_punishment(update, context, "إرسال صورة")
        return
    
    if settings.get("antisticker", 0) and update.message.sticker:
        await apply_punishment(update, context, "إرسال ملصق")
        return
    
    if settings.get("antivideo", 0) and update.message.video:
        await apply_punishment(update, context, "إرسال فيديو")
        return
    
    if settings.get("antibot", 1) and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            if member.is_bot:
                await context.bot.ban_chat_member(chat_id, member.id)
                await update.message.reply_text(f"🚫 تم حظر البوت: {member.full_name}")

async def apply_punishment(update: Update, context: ContextTypes.DEFAULT_TYPE, reason: str, user_id: int = None):
    chat_id = update.effective_chat.id
    target_id = user_id or update.effective_user.id
    
    if target_id == ADMIN_ID or target_id == context.bot.id:
        return
    
    settings = db.get_settings(chat_id)
    punish_type = settings.get("punish_type", "mute")
    
    try:
        await update.message.delete()
        await asyncio.sleep(0.5)
        
        if punish_type == "ban":
            await context.bot.ban_chat_member(chat_id, target_id)
            await update.message.reply_text(
                f"🚫 **تم حظر العضو**\n⚠️ السبب: {reason}",
                parse_mode=ParseMode.MARKDOWN
            )
        elif punish_type == "kick":
            await context.bot.ban_chat_member(chat_id, target_id)
            await context.bot.unban_chat_member(chat_id, target_id)
            await update.message.reply_text(
                f"⚠️ **تم طرد العضو**\n⚠️ السبب: {reason}",
                parse_mode=ParseMode.MARKDOWN
            )
        elif punish_type == "mute":
            minutes = settings.get("mute_minutes", 60)
            until = datetime.now() + timedelta(minutes=minutes)
            await context.bot.restrict_chat_member(
                chat_id, target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await update.message.reply_text(
                f"🔇 **تم كتم العضو**\n⏱️ المدة: {minutes} دقيقة\n⚠️ السبب: {reason}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔓 فك الكتم", callback_data=f"unmute_{target_id}_{chat_id}")]
                ])
            )
    except Exception as e:
        logging.error(f"Punishment error: {e}")

# ==================== الترحيب ====================
async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    settings = db.get_settings(chat_id)
    
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        
        name = member.full_name
        username = f"@{member.username}" if member.username else "لا يوجد"
        user_id = member.id
        
        if settings.get("captcha_enabled", 0):
            code = await generate_captcha()
            db.save_captcha(chat_id, user_id, code)
            
            await context.bot.send_message(
                chat_id,
                f"🤖 **تحقق من أنك لست روبوتاً**\n\n"
                f"👤 {name}\n"
                f"📝 أرسل الرمز التالي للتحقق:\n"
                f"`{code}`\n\n"
                f"⏱️ لديك {CAPTCHA_TIMEOUT} ثانية للتحقق.",
                parse_mode=ParseMode.MARKDOWN
            )
        
        if settings.get("welcome_enabled", 1):
            welcome = settings.get("welcome_text", "") or f"""🌿 **أهلاً وسهلاً بك في القروب** 🌿

👤 **الاسم:** {name}
🆔 **اليوزر:** {username}
🆔 **الايدي:** `{user_id}`

💙 نورت القروب معانا!"""
            
            welcome_photo = settings.get("welcome_photo", "")
            photo_to_use = welcome_photo if welcome_photo else WELCOME_IMAGE
            
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_to_use,
                    caption=welcome,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("👨‍💻 المطور @MRDPY", url="https://t.me/MRDPY")]
                    ])
                )
            except Exception as e:
                logging.error(f"Welcome error: {e}")
                # Fallback to text
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=welcome,
                    parse_mode=ParseMode.MARKDOWN
                )

# ==================== معالجات الكول باك ====================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("unmute_"):
        _, target_user_id, chat_id = data.split("_")
        target_user_id = int(target_user_id)
        chat_id = int(chat_id)
        
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        
        try:
            await context.bot.restrict_chat_member(
                chat_id, target_user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_media=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
            await query.edit_message_text("✅ تم فك الكتم بنجاح")
        except Exception as e:
            await query.answer(f"فشل فك الكتم: {e}", show_alert=True)
        return
    
    if data == "back_main":
        if user_id == ADMIN_ID:
            await query.edit_message_text(
                "🤖 **لوحة تحكم المطور**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=admin_panel_keyboard()
            )
        else:
            await query.edit_message_text(
                "🤖 **القائمة الرئيسية**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_keyboard()
            )
        return
    
    if data == "user_panel":
        if user_id != ADMIN_ID:
            await query.answer("هذه اللوحة للمطور فقط", show_alert=True)
            return
        await query.edit_message_text(
            "👤 **لوحة المستخدمين**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_keyboard()
        )
        return
    
    if data == "my_groups":
        groups = db.get_user_groups(user_id)
        if not groups:
            await query.edit_message_text(
                "📋 لم يتم العثور على مجموعات.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
                ])
            )
            return
        await query.edit_message_text(
            f"📋 **مجموعاتك:** {len(groups)}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=groups_keyboard(groups, 0)
        )
        return
    
    if data.startswith("groups_page_"):
        page = int(data.split("_")[2])
        groups = db.get_user_groups(user_id)
        await query.edit_message_text(
            f"📋 **مجموعاتك:** {len(groups)}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=groups_keyboard(groups, page)
        )
        return
    
    if data.startswith("group_"):
        chat_id = int(data.split("_")[1])
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        if not await is_bot_admin(chat_id, context):
            await query.answer("البوت ليس مشرفاً", show_alert=True)
            return
        
        chat = await context.bot.get_chat(chat_id)
        await query.edit_message_text(
            f"🛡️ **لوحة حماية: {chat.title}**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=panel_keyboard(chat_id)
        )
        return
    
    if data.startswith("toggle_"):
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        
        setting = data.replace("toggle_", "")
        settings = db.get_settings(chat_id)
        current = settings.get(setting, 0)
        new_value = 0 if current else 1
        db.update_setting(chat_id, setting, new_value)
        await query.answer(f"تم {'تفعيل' if new_value else 'تعطيل'}")
        
        chat = await context.bot.get_chat(chat_id)
        await query.edit_message_text(
            f"🛡️ **لوحة حماية: {chat.title}**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=panel_keyboard(chat_id)
        )
        return
    
    if data == "set_punishment":
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        await query.edit_message_text(
            "⚖️ **اختر نوع العقوبة:**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=punishment_keyboard()
        )
        return
    
    if data.startswith("punish_"):
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        
        punish_type = data.replace("punish_", "")
        db.update_setting(chat_id, "punish_type", punish_type)
        await query.answer(f"تم تعيين العقوبة: {punish_type}")
        
        if punish_type == "mute":
            await query.edit_message_text(
                "⏱️ **اختر مدة الكتم:**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=mute_time_keyboard()
            )
        else:
            chat = await context.bot.get_chat(chat_id)
            await query.edit_message_text(
                f"🛡️ **لوحة حماية: {chat.title}**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=panel_keyboard(chat_id)
            )
        return
    
    if data.startswith("mute_"):
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        
        minutes = int(data.split("_")[1])
        db.update_setting(chat_id, "mute_minutes", minutes)
        await query.answer(f"تم تعيين مدة الكتم: {minutes} دقيقة")
        
        chat = await context.bot.get_chat(chat_id)
        await query.edit_message_text(
            f"🛡️ **لوحة حماية: {chat.title}**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=panel_keyboard(chat_id)
        )
        return
    
    if data == "set_mute_time":
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        await query.edit_message_text(
            "⏱️ **اختر مدة الكتم:**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=mute_time_keyboard()
        )
        return
    
    if data == "set_delete_time":
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        await query.edit_message_text(
            "⏱️ **اختر مدة الحذف التلقائي:**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=delete_time_keyboard()
        )
        return
    
    if data.startswith("delete_"):
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        
        seconds = int(data.split("_")[1])
        db.update_setting(chat_id, "delete_seconds", seconds)
        await query.answer(f"تم تعيين مدة الحذف: {seconds} ثانية")
        
        chat = await context.bot.get_chat(chat_id)
        await query.edit_message_text(
            f"🛡️ **لوحة حماية: {chat.title}**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=panel_keyboard(chat_id)
        )
        return
    
    if data == "edit_badwords":
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        
        context.user_data["state"] = f"waiting_badwords_{chat_id}"
        await query.edit_message_text(
            "📝 **أرسل الكلمات السيئة مفصولة بفاصلة**\nمثال: كلمة1,كلمة2,كلمة3\n\n🔹 أرسل 'حذف' لحذف كل الكلمات\n🔹 أرسل 'عرض' لعرض الكلمات الحالية",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="panel")]
            ])
        )
        return
    
    if data == "help":
        await query.edit_message_text(
            f"📖 **دليل استخدام البوت**\n\n"
            f"🔹 **الأوامر الأساسية:**\n"
            f"/start - بدء البوت\n"
            f"/panel - لوحة التحكم\n"
            f"/mute @user - كتم عضو\n"
            f"/unmute @user - فك الكتم\n"
            f"/ban @user - حظر عضو\n"
            f"/kick @user - طرد عضو\n"
            f"/report @user سبب - إبلاغ عن عضو\n"
            f"/stats - إحصائيات المجموعة\n\n"
            f"📸 **أوامر الصور:**\n"
            f"/setwelcomephoto - تغيير صورة ترحيب المجموعة\n"
            f"/setprivatephoto - تغيير صورة ترحيب الخاص\n"
            f"/resetwelcomephoto - إعادة تعيين صورة الترحيب",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ])
        )
        return
    
    if data in ["broadcast_all", "broadcast_groups"]:
        if user_id != ADMIN_ID:
            await query.answer("للمطور فقط", show_alert=True)
            return
        
        context.user_data["broadcast_type"] = "all" if data == "broadcast_all" else "groups"
        await query.edit_message_text(
            "📢 **أرسل رسالة الإذاعة الآن**\nسيتم إرسالها لكافة المستخدمين/المجموعات.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ])
        )
        return
    
    if data == "stats_user":
        users_count = len(db.get_all_users())
        groups = db.get_user_groups(user_id)
        await query.edit_message_text(
            f"📊 **إحصائياتك**\n👥 المجموعات: {len(groups)}\n👤 المستخدمين المسجلين: {users_count}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ])
        )
        return
    
    if data == "stats_admin" and user_id == ADMIN_ID:
        users = len(db.get_all_users())
        groups = len(db.get_user_groups(ADMIN_ID))
        await query.edit_message_text(
            f"📊 **إحصائيات البوت**\n👥 المستخدمين: {users}\n👥 المجموعات: {groups}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ])
        )
        return
    
    if data == "global_ban" and user_id == ADMIN_ID:
        await query.edit_message_text(
            "🚫 **الحظر العالمي**\n\n📝 استخدم الأمر:\n/globalban @user سبب",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ])
        )
        return
    
    if data == "reports_list" and user_id == ADMIN_ID:
        db.cur.execute("SELECT id, user_id, reporter_id, reason, status, created_at FROM reports ORDER BY id DESC LIMIT 20")
        reports = db.cur.fetchall()
        
        if not reports:
            await query.edit_message_text(
                "📋 لا توجد تقارير.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
                ])
            )
            return
        
        text = "📋 **آخر 20 تقرير:**\n\n"
        for report in reports:
            text += f"#{report[0]} - {report[5]}\n"
            text += f"👤 العضو: `{report[1]}`\n"
            text += f"📝 السبب: {report[3]}\n"
            text += f"📌 الحالة: {report[4]}\n\n"
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
            ])
        )
        return
    
    if data == "reset_settings":
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        
        # Reset to defaults
        defaults = {
            'antilink': 1, 'antibadword': 1, 'antispam': 1,
            'antiphoto': 0, 'antisticker': 0, 'antivideo': 0,
            'antireply': 0, 'antibot': 1, 'antiurl': 1,
            'badwords': 'كس,خا,زق,حرام,شرموطة,عاهرة,قحبة,منيوك,نايك,لوطي,مثلي,زب,كوس',
            'punish_type': 'mute', 'mute_minutes': 60,
            'welcome_enabled': 1, 'welcome_text': '',
            'force_subscribe': 0, 'security_mode': 0,
            'log_channel': 0, 'captcha_enabled': 0,
            'auto_delete': 0, 'delete_seconds': 60,
            'welcome_photo': ''
        }
        
        for key, value in defaults.items():
            db.update_setting(chat_id, key, value)
        
        await query.answer("تم إعادة ضبط الإعدادات")
        chat = await context.bot.get_chat(chat_id)
        await query.edit_message_text(
            f"🛡️ **لوحة حماية: {chat.title}**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=panel_keyboard(chat_id)
        )
        return
    
    if data == "change_welcome_photo":
        chat_id = query.message.chat.id
        if not await is_admin(chat_id, user_id, context):
            await query.answer("للمشرفين فقط", show_alert=True)
            return
        
        await query.edit_message_text(
            "📸 **تغيير صورة الترحيب**\n\nأرسل الصورة التي تريدها ورد على الصورة بـ:\n`/setwelcomephoto`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="panel")]
            ])
        )
        return
    
    await query.answer("⚠️ أمر غير معروف", show_alert=True)

# ==================== أوامر المشرفين ====================
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(chat_id, user_id, context):
        return
    
    if not context.args:
        await update.message.reply_text("استخدام: /mute @username أو بالرد على رسالة العضو")
        return
    
    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user.id
    else:
        username = context.args[0].replace("@", "")
        try:
            members = await context.bot.get_chat_administrators(chat_id)
            for m in members:
                if m.user.username and m.user.username.lower() == username.lower():
                    target = m.user.id
                    break
        except Exception:
            pass
    
    if not target:
        await update.message.reply_text("❌ لم يتم العثور على العضو.")
        return
    
    settings = db.get_settings(chat_id)
    minutes = settings.get("mute_minutes", 60)
    until = datetime.now() + timedelta(minutes=minutes)
    
    try:
        await context.bot.restrict_chat_member(
            chat_id, target,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )
        await update.message.reply_text(f"🔇 تم كتم العضو لمدة {minutes} دقيقة.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(chat_id, user_id, context):
        return
    
    if not context.args:
        await update.message.reply_text("استخدام: /unmute @username")
        return
    
    username = context.args[0].replace("@", "")
    target = None
    try:
        members = await context.bot.get_chat_administrators(chat_id)
        for m in members:
            if m.user.username and m.user.username.lower() == username.lower():
                target = m.user.id
                break
    except Exception:
        pass
    
    if not target:
        await update.message.reply_text("❌ لم يتم العثور على العضو.")
        return
    
    try:
        await context.bot.restrict_chat_member(
            chat_id, target,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await update.message.reply_text(f"✅ تم فك الكتم عن @{username}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(chat_id, user_id, context):
        return
    
    if not context.args:
        await update.message.reply_text("استخدام: /ban @username")
        return
    
    username = context.args[0].replace("@", "")
    target = None
    try:
        members = await context.bot.get_chat_administrators(chat_id)
        for m in members:
            if m.user.username and m.user.username.lower() == username.lower():
                target = m.user.id
                break
    except Exception:
        pass
    
    if not target:
        await update.message.reply_text("❌ لم يتم العثور على العضو.")
        return
    
    try:
        await context.bot.ban_chat_member(chat_id, target)
        await update.message.reply_text(f"🚫 تم حظر @{username}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_admin(chat_id, user_id, context):
        return
    
    if not context.args:
        await update.message.reply_text("استخدام: /kick @username")
        return
    
    username = context.args[0].replace("@", "")
    target = None
    try:
        members = await context.bot.get_chat_administrators(chat_id)
        for m in members:
            if m.user.username and m.user.username.lower() == username.lower():
                target = m.user.id
                break
    except Exception:
        pass
    
    if not target:
        await update.message.reply_text("❌ لم يتم العثور على العضو.")
        return
    
    try:
        await context.bot.ban_chat_member(chat_id, target)
        await context.bot.unban_chat_member(chat_id, target)
        await update.message.reply_text(f"⚠️ تم طرد @{username}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("استخدام: /report @user سبب التبليغ")
        return
    
    username = context.args[0].replace("@", "")
    reason = " ".join(context.args[1:]) or "لا يوجد سبب"
    
    target = None
    try:
        members = await context.bot.get_chat_administrators(chat_id)
        for m in members:
            if m.user.username and m.user.username.lower() == username.lower():
                target = m.user.id
                break
    except Exception:
        pass
    
    if not target:
        await update.message.reply_text("❌ لم يتم العثور على العضو.")
        return
    
    report_id = db.add_report(chat_id, target, user_id, reason)
    await update.message.reply_text(
        f"✅ **تم الإبلاغ بنجاح**\n"
        f"👤 العضو: @{username}\n"
        f"📝 السبب: {reason}\n"
        f"🆔 رقم البلاغ: #{report_id}",
        parse_mode=ParseMode.MARKDOWN
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)
    
    await update.message.reply_text(
        f"📊 **إحصائيات المجموعة**\n\n"
        f"🔹 **الإعدادات:**\n"
        f"• مضاد الروابط: {'✅' if settings.get('antilink',1) else '❌'}\n"
        f"• مضاد الكلمات: {'✅' if settings.get('antibadword',1) else '❌'}\n"
        f"• مضاد السبام: {'✅' if settings.get('antispam',1) else '❌'}\n"
        f"• منع الصور: {'✅' if settings.get('antiphoto',0) else '❌'}\n"
        f"• منع الفيديو: {'✅' if settings.get('antivideo',0) else '❌'}\n"
        f"• منع البوتات: {'✅' if settings.get('antibot',1) else '❌'}\n"
        f"• الترحيب: {'✅' if settings.get('welcome_enabled',1) else '❌'}\n"
        f"• الكابتشا: {'✅' if settings.get('captcha_enabled',0) else '❌'}\n"
        f"• الحذف التلقائي: {'✅' if settings.get('auto_delete',0) else '❌'}\n"
        f"• الوضع الأمني: {'✅' if settings.get('security_mode',0) else '❌'}\n\n"
        f"⚖️ **نوع العقوبة:** {settings.get('punish_type', 'mute')}\n"
        f"⏱️ **مدة الكتم:** {settings.get('mute_minutes', 60)} دقيقة",
        parse_mode=ParseMode.MARKDOWN
    )

async def global_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ للمطور فقط.")
        return
    
    if not context.args:
        await update.message.reply_text("استخدام: /globalban @user سبب")
        return
    
    username = context.args[0].replace("@", "")
    reason = " ".join(context.args[1:]) or "لا يوجد سبب"
    
    target = None
    try:
        members = await context.bot.get_chat_administrators(update.effective_chat.id)
        for m in members:
            if m.user.username and m.user.username.lower() == username.lower():
                target = m.user.id
                break
    except Exception:
        pass
    
    if not target:
        await update.message.reply_text("❌ لم يتم العثور على العضو.")
        return
    
    db.add_global_ban(target, reason, ADMIN_ID)
    await update.message.reply_text(
        f"🚫 **تم الحظر العالمي**\n👤 @{username}\n📝 السبب: {reason}",
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== معالجة الكلمات السيئة ====================
async def handle_badwords_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state", "")
    if not state.startswith("waiting_badwords_"):
        return
    
    chat_id = int(state.split("_")[2])
    text = update.message.text.strip()
    
    if not await is_admin(chat_id, update.effective_user.id, context):
        await update.message.reply_text("⛔ ليس لديك صلاحية.")
        return
    
    settings = db.get_settings(chat_id)
    
    if text.lower() == "حذف":
        db.update_setting(chat_id, "badwords", "")
        await update.message.reply_text("✅ تم حذف كل الكلمات السيئة")
    elif text.lower() == "عرض":
        words = settings.get("badwords", [])
        if words:
            await update.message.reply_text(f"📝 **الكلمات السيئة الحالية:**\n{', '.join(words)}")
        else:
            await update.message.reply_text("📝 لا توجد كلمات سيئة محفوظة.")
    else:
        words = [w.strip() for w in text.split(",") if w.strip()]
        db.update_setting(chat_id, "badwords", ",".join(words))
        await update.message.reply_text(f"✅ تم حفظ الكلمات السيئة:\n{', '.join(words)}")
    
    context.user_data.pop("state", None)

# ==================== معالجة الإذاعة ====================
async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    b_type = context.user_data.get("broadcast_type")
    if not b_type:
        return
    
    msg = update.message
    sent = 0
    fail = 0
    
    if b_type == "all":
        users = db.get_all_users()
        for uid in users:
            try:
                await msg.copy(uid)
                sent += 1
                await asyncio.sleep(0.1)
            except Exception:
                fail += 1
    elif b_type == "groups":
        groups = db.get_user_groups(ADMIN_ID)
        for group in groups:
            try:
                await msg.copy(group["id"])
                sent += 1
                await asyncio.sleep(0.1)
            except Exception:
                fail += 1
    
    await update.message.reply_text(
        f"✅ **تم الإرسال**\nنجح: {sent}\nفشل: {fail}",
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data.pop("broadcast_type", None)

# ==================== الحذف التلقائي ====================
async def auto_delete_loop(context: ContextTypes.DEFAULT_TYPE):
    messages = db.get_auto_delete_messages()
    for chat_id, message_id, user_id in messages:
        try:
            await context.bot.delete_message(chat_id, message_id)
            db.remove_auto_delete(chat_id, message_id)
        except Exception:
            pass

# ==================== Flask Webhook ====================
application = None

@app_flask.route('/', methods=['GET'])
def index():
    return jsonify({"status": "Bot is running", "token": "Active"})

@app_flask.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        try:
            data = request.get_json(force=True)
            update = Update.de_json(data, application.bot)
            asyncio.create_task(application.process_update(update))
            return jsonify({"status": "ok"})
        except Exception as e:
            logging.error(f"Webhook error: {e}")
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Invalid content type"}), 400

# ==================== التشغيل ====================
async def setup_bot():
    global application, BOT_USERNAME
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    bot_info = await application.bot.get_me()
    BOT_USERNAME = bot_info.username
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("panel", panel_command))
    application.add_handler(CommandHandler("mute", mute_command))
    application.add_handler(CommandHandler("unmute", unmute_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("kick", kick_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("globalban", global_ban_command))
    application.add_handler(CommandHandler("setwelcomephoto", set_group_welcome_photo))
    application.add_handler(CommandHandler("setprivatephoto", set_private_welcome_photo))
    application.add_handler(CommandHandler("resetwelcomephoto", reset_welcome_photo))
    
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Sticker.ALL, handle_media))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Chat(ADMIN_ID), handle_broadcast))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_badwords_input))
    
    # Job queue
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(auto_delete_loop, interval=10, first=10)
    
    # Set webhook
    webhook_url = "https://YOUR_RENDER_URL/webhook"  # CHANGE THIS
    await application.bot.set_webhook(webhook_url)
    
    print(f"✅ Bot @{BOT_USERNAME} is running with webhook")
    return application

async def run_application():
    app = await setup_bot()
    # Keep the bot running
    while True:
        await asyncio.sleep(1)

def start_flask():
    app_flask.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    # Start Flask in a separate thread
    from threading import Thread
    flask_thread = Thread(target=start_flask)
    flask_thread.start()
    
    # Run the bot
    asyncio.run(run_application())
