#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, logging, html, datetime, re, asyncio
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8613059695:AAHFV4oP7_24UGkBFr5CwrDu9W8rzFb2T3w"
OWNER_ID = 7093004518
DEV_USERNAME = "@MRDPY" # اليوزر حقك
DELETE_LINKS = True

# قائمة كلمات قبيحة شاملة - ضيف عليها براحتك
GROUP_SETTINGS = {
    "welcome_img": "https://files.catbox.moe/lnc37z.jpg",
    "rules": "1. ممنوع السب والشتم والعنصرية\n2. ممنوع الروابط والاعلانات\n3. احترام الاعضاء والادارة\n4. المخالفة = كتم ثم طرد",
    "bad_words": [
        "كسمك", "كسم", "شرموط", "شرموطة", "عرص", "عرصه", "قحبه", "قحب",
        "منيك", "نيك", "متناك", "متناكه", "كس", "زب", "طيز", "خرا", "خول",
        "fuck", "shit", "bitch", "asshole", "cunt", "dick" # انجليزي كمان
    ]
}

warnings = defaultdict(int)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== دالة العقوبة الحازمة ==========
async def punish_user(update: Update, context: ContextTypes.DEFAULT_TYPE, reason: str, hard=False):
    user = update.message.from_user
    chat_id = update.effective_chat.id
    user_id = user.id
    safe_name = html.escape(user.full_name)

    warnings[user_id] += 1
    count = warnings[user_id]

    if hard or count >= 2: # كلمة سيئة = عقوبة سريعة
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await context.bot.unban_chat_member(chat_id, user_id)
            msg = await update.message.reply_text(f"⛔️ <b>تم طرد</b> {safe_name}\nالسبب: {reason}", parse_mode="HTML")
            warnings[user_id] = 0
        except: msg = await update.message.reply_text("❌ ما عندي صلاحية طرد")
    else:
        try:
            until = datetime.datetime.now() + datetime.timedelta(minutes=10)
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=update.message.chat.permissions, until_date=until)
            msg = await update.message.reply_text(f"🔇 <b>تم كتم</b> {safe_name} 10 دقايق\nالسبب: {reason}\nانذار {count}/2", parse_mode="HTML")
        except: msg = await update.message.reply_text("❌ ما عندي صلاحية كتم")

    await asyncio.sleep(6)
    await msg.delete()

# ========== فحص الرسائل ==========
async def filter_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    if update.effective_user.id == OWNER_ID: return # المطور معفي

    text = update.message.text.lower()
    user_id = update.effective_user.id

    # 1. الروابط = انذارات
    if DELETE_LINKS and re.search(r'(http[s]?://\S+|t\.me/\S+|@\w+)', text, re.IGNORECASE):
        await update.message.delete()
        warnings[user_id] += 1
        if warnings[user_id] >= 3:
            await punish_user(update, context, "تكرار نشر الروابط", hard=True)
        else:
            await update.message.reply_text(f"⚠️ <b>ممنوع الروابط</b> انذار {warnings[user_id]}/3", parse_mode="HTML")
        return

    # 2. الكلمات القبيحة = كتم طوالي ثم طرد
    for bad_word in GROUP_SETTINGS["bad_words"]:
        if re.search(r'\b' + re.escape(bad_word) + r'\b', text): # يمسك الكلمة كاملة
            await update.message.delete()
            await punish_user(update, context, f"استخدام لفظ مسيء: {bad_word}", hard=True)
            return

# ========== الترحيب + زر المطور ==========
async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group_title = html.escape(update.effective_chat.title)
    group_username = update.effective_chat.username
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        safe_name = html.escape(member.full_name)
        user_id = member.id
        username = f"@{member.username}" if member.username else "لا يوجد"
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2)))
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%I:%M %p")

        caption = (
            f"🎉 <b>أهلاً بيك في {group_title}</b> 🎉\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>الاسم:</b> {safe_name}\n"
            f"🆔 <b>الايدي:</b> <code>{user_id}</code>\n"
            f"🔗 <b>اليوزر:</b> {username}\n"
            f"📅 <b>تاريخ الدخول:</b> {date_str}\n"
            f"⏰ <b>الوقت:</b> {time_str}\n\n"
            f"━━━━━━━━━━\n"
            f"📜 <b>قوانين {group_title}:</b>\n"
            f"<pre>{GROUP_SETTINGS['rules']}</pre>\n"
            f"━━━━━━━━━━\n"
            f"⚠️ البوت حازم: كلمة واحدة = كتم"
        )

        # زرين: القروب + المطور
        keyboard = []
        if group_username:
            keyboard.append([InlineKeyboardButton(f"📢 {group_title}", url=f"https://t.me/{group_username}")])
        keyboard.append([InlineKeyboardButton(f"👑 المطور {DEV_USERNAME}", url=f"https://t.me/{DEV_USERNAME.replace('@','')}")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=GROUP_SETTINGS["welcome_img"], caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        except: await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode="HTML")

# ========== اوامر المطور ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🛡️ <b>بوت حماية حازم</b>\n\n"
        f"/addbadword &lt;كلمة&gt; - اضافة كلمة\n"
        f"/removebadword &lt;كلمة&gt; - حذف كلمة\n"
        f"/badwords - عرض القائمة\n"
        f"/togglelinks - تشغيل/ايقاف حذف الروابط",
        parse_mode="HTML"
    )

async def add_bad_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= OWNER_ID: return
    if context.args:
        word = context.args[0].lower()
        if word not in GROUP_SETTINGS["bad_words"]:
            GROUP_SETTINGS["bad_words"].append(word)
            await update.message.reply_text(f"✅ تمت اضافة: `{word}`", parse_mode="HTML")

async def remove_bad_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= OWNER_ID: return
    if context.args:
        word = context.args[0].lower()
        if word in GROUP_SETTINGS["bad_words"]:
            GROUP_SETTINGS["bad_words"].remove(word)
            await update.message.reply_text(f"✅ تم حذف: `{word}`", parse_mode="HTML")

async def list_bad_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= OWNER_ID: return
    words = "\n".join([f"- {w}" for w in GROUP_SETTINGS["bad_words"]])
    await update.message.reply_text(f"📜 <b>قائمة الكلمات الممنوعة {len(GROUP_SETTINGS['bad_words'])} كلمة:</b>\n{words}", parse_mode="HTML")

async def set_welcome_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= OWNER_ID: return
    if context.args: GROUP_SETTINGS["welcome_img"] = context.args[0]; await update.message.reply_text("✅ تم تغيير الصورة")

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= OWNER_ID: return
    if context.args: GROUP_SETTINGS["rules"] = "\n".join(context.args); await update.message.reply_text("✅ تم تغيير القوانين")

async def toggle_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= OWNER_ID: return
    global DELETE_LINKS; DELETE_LINKS = not DELETE_LINKS
    await update.message.reply_text(f"🛡️ حذف الروابط: {'مفعل ✅' if DELETE_LINKS else 'معطل ❌'}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setwelcome", set_welcome_image))
    app.add_handler(CommandHandler("setrules", set_rules))
    app.add_handler(CommandHandler("togglelinks", toggle_links))
    app.add_handler(CommandHandler("addbadword", add_bad_word))
    app.add_handler(CommandHandler("removebadword", remove_bad_word))
    app.add_handler(CommandHandler("badwords", list_bad_words))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, filter_messages))
    logger.info("🚀 البوت الحازم شغال...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__": main()
