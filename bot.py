#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import base64
import json
import gzip
import zlib
import logging
import time
import binascii
import hashlib
import requests
import urllib.parse
import html
import datetime
import asyncio
from collections import defaultdict
from typing import Dict, Any, Optional, List, Tuple

# ========== مكتبات الطرف الثالث ==========
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatMemberStatus

# محاولة استيراد مكتبات التشفير
try:
    from Crypto.Cipher import AES, ARC4, Blowfish, DES
    from Crypto.Util.Padding import unpad
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logging.warning("PyCryptodome not available - AES/RC4/Blowfish/DES decryption disabled")

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    logging.warning("Cryptography not available - Fernet decryption disabled")

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

try:
    import filetype
    FILETYPE_AVAILABLE = True
except ImportError:
    FILETYPE_AVAILABLE = False

# ========== التوكن والإعدادات ==========
TOKEN = os.getenv("TOKEN", "8613059695:AAHFV4oP7_24UGkBFr5CwrDu9W8rzFb2T3w")
OWNER_ID = int(os.getenv("OWNER_ID", "7093004518"))
ALLOWED_GROUPS = {}
CONFIG_FILE = "group_config.json"
DELETE_LINKS = True
GROUP_SETTINGS = {
    "welcome_img": "https://files.catbox.moe/lnc37z.jpg",
    "rules": "1. ممنوع السب والشتم\n2. ممنوع الروابط والاعلانات\n3. احترام الاعضاء\n4. المخالفة = انذار ثم طرد",
    "bad_words": ["كسمك", "شرموط", "عرص", "احا"]
}
warnings = defaultdict(int)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== دوال الحفظ والتحميل ==========
def save_group_config(groups: dict):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"groups": groups}, f)
    except Exception as e:
        logger.error(f"Error saving config: {e}")

def load_group_config() -> dict:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data.get('groups', {})
    except Exception as e:
        logger.error(f"Error loading config: {e}")
    return {}

# ========== دوال فك التشفير الأساسية ==========

def decode_base64(text: str) -> str:
    try:
        missing_padding = len(text) % 4
        if missing_padding:
            text += '=' * (4 - missing_padding)
        return base64.b64decode(text).decode('utf-8', errors='ignore')
    except:
        try:
            return base64.urlsafe_b64decode(text).decode('utf-8', errors='ignore')
        except:
            return text

def decode_hex(text: str) -> str:
    try:
        text = re.sub(r'^0x', '', text)
        return bytes.fromhex(text).decode('utf-8', errors='ignore')
    except:
        return text

def decode_url(text: str) -> str:
    try:
        return urllib.parse.unquote_plus(text)
    except:
        return text

def decode_caesar(text: str, shift: int = None) -> str:
    if shift is None:
        best = text
        best_score = 0
        for s in range(1, 26):
            result = decode_caesar_shift(text, s)
            score = sum(1 for c in result if c.isalpha() and c.lower() in 'etaoinshrdlcumwfgypbvkjxqz')
            if score > best_score:
                best_score = score
                best = result
        return best
    return decode_caesar_shift(text, shift)

def decode_caesar_shift(text: str, shift: int) -> str:
    result = []
    for c in text:
        if 'a' <= c <= 'z':
            result.append(chr((ord(c) - ord('a') + shift) % 26 + ord('a')))
        elif 'A' <= c <= 'Z':
            result.append(chr((ord(c) - ord('A') + shift) % 26 + ord('A')))
        else:
            result.append(c)
    return ''.join(result)

def decode_rot13(text: str) -> str:
    return decode_caesar_shift(text, 13)

def decode_xor(text: str, key: str = None) -> str:
    if key is None:
        for k in ['key', 'secret', 'password', 'admin', '1234', 'abcd']:
            try:
                result = decode_xor_key(text, k)
                if re.search(r'\b(the|and|for|you|that|this|is|are|was|were)\b', result, re.I):
                    return result
            except:
                pass
        return text
    return decode_xor_key(text, key)

def decode_xor_key(text: str, key: str) -> str:
    try:
        decoded = ''.join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(text))
        return decoded
    except:
        return text

def decode_gzip(text: str) -> str:
    try:
        return gzip.decompress(bytes.fromhex(text)).decode('utf-8', errors='ignore')
    except:
        try:
            return gzip.decompress(text.encode()).decode('utf-8', errors='ignore')
        except:
            return text

def decode_zlib(text: str) -> str:
    try:
        return zlib.decompress(bytes.fromhex(text)).decode('utf-8', errors='ignore')
    except:
        try:
            return zlib.decompress(text.encode()).decode('utf-8', errors='ignore')
        except:
            return text

def decode_aes(text: str, key: str = None) -> str:
    if not CRYPTO_AVAILABLE:
        return text
    try:
        if key is None:
            for k in ['key', 'secret', 'password', 'admin', '1234', 'abcd']:
                try:
                    key_hash = hashlib.sha256(k.encode()).digest()
                    cipher = AES.new(key_hash, AES.MODE_ECB)
                    decoded = cipher.decrypt(bytes.fromhex(text)).decode('utf-8', errors='ignore')
                    if decoded and re.search(r'\b(the|and|for|you|that|this)\b', decoded, re.I):
                        return decoded
                except:
                    pass
        else:
            key_hash = hashlib.sha256(key.encode()).digest()
            cipher = AES.new(key_hash, AES.MODE_ECB)
            decoded = cipher.decrypt(bytes.fromhex(text)).decode('utf-8', errors='ignore')
            return decoded
    except:
        pass
    return text

def decode_rc4(text: str, key: str = None) -> str:
    if not CRYPTO_AVAILABLE:
        return text
    try:
        if key is None:
            for k in ['key', 'secret', 'password']:
                try:
                    cipher = ARC4.new(k.encode())
                    decoded = cipher.decrypt(bytes.fromhex(text)).decode('utf-8', errors='ignore')
                    if decoded and re.search(r'\b(the|and|for|you|that|this)\b', decoded, re.I):
                        return decoded
                except:
                    pass
        else:
            cipher = ARC4.new(key.encode())
            decoded = cipher.decrypt(bytes.fromhex(text)).decode('utf-8', errors='ignore')
            return decoded
    except:
        pass
    return text

def decode_blowfish(text: str, key: str = None) -> str:
    if not CRYPTO_AVAILABLE:
        return text
    try:
        if key is None:
            for k in ['key', 'secret', 'password']:
                try:
                    cipher = Blowfish.new(k.encode(), Blowfish.MODE_ECB)
                    decoded = cipher.decrypt(bytes.fromhex(text)).decode('utf-8', errors='ignore')
                    if decoded and re.search(r'\b(the|and|for|you|that|this)\b', decoded, re.I):
                        return decoded
                except:
                    pass
        else:
            cipher = Blowfish.new(key.encode(), Blowfish.MODE_ECB)
            decoded = cipher.decrypt(bytes.fromhex(text)).decode('utf-8', errors='ignore')
            return decoded
    except:
        pass
    return text

def decode_des(text: str, key: str = None) -> str:
    if not CRYPTO_AVAILABLE:
        return text
    try:
        if key is None:
            for k in ['key', 'secret', 'password']:
                try:
                    key_bytes = k.encode()[:8].ljust(8, b'\0')
                    cipher = DES.new(key_bytes, DES.MODE_ECB)
                    decoded = cipher.decrypt(bytes.fromhex(text)).decode('utf-8', errors='ignore')
                    if decoded and re.search(r'\b(the|and|for|you|that|this)\b', decoded, re.I):
                        return decoded
                except:
                    pass
        else:
            key_bytes = key.encode()[:8].ljust(8, b'\0')
            cipher = DES.new(key_bytes, DES.MODE_ECB)
            decoded = cipher.decrypt(bytes.fromhex(text)).decode('utf-8', errors='ignore')
            return decoded
    except:
        pass
    return text

def decode_fernet(text: str, key: str = None) -> str:
    if not CRYPTOGRAPHY_AVAILABLE:
        return text
    try:
        if key is None:
            for k in ['key', 'secret', 'password']:
                try:
                    f = Fernet(base64.urlsafe_b64encode(k.encode().ljust(32, b'\0')))
                    decoded = f.decrypt(text.encode()).decode('utf-8', errors='ignore')
                    if decoded and re.search(r'\b(the|and|for|you|that|this)\b', decoded, re.I):
                        return decoded
                except:
                    pass
        else:
            f = Fernet(base64.urlsafe_b64encode(key.encode().ljust(32, b'\0')))
            decoded = f.decrypt(text.encode()).decode('utf-8', errors='ignore')
            return decoded
    except:
        pass
    return text

# ========== دوال استخراج المعلومات ==========

def extract_passwords(content: str) -> List[str]:
    passwords = []
    patterns = [
        r'(?:password|pass|key|secret|pwd|token|api_key|apikey)\s*[:=]\s*([^\s"\']+)',
        r'(?:password|pass|key|secret|pwd|token|api_key|apikey)\s*=\s*["\']([^"\']+)["\']',
        r'["\'](?:password|pass|key|secret|pwd|token|api_key|apikey)["\']\s*:\s*["\']([^"\']+)["\']',
        r'[A-Za-z0-9+/]{20,}={0,2}',
        r'[0-9a-fA-F]{32,}',
        r'[A-Za-z]{10,}[0-9]{4,}'
    ]
    for pattern in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        passwords.extend(matches)
    return list(set(passwords))

def clean_corrupted_text(text: str) -> str:
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF\u0500-\u052F\u1F00-\u1FFF\u2C00-\u2C5F\uA000-\uA48F\uA4D0-\uA4FF\uA840-\uA87F\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F\uFF00-\uFFEF,.!?;:() ]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ========== محرك الفك التلقائي المتسلسل ==========

def auto_decode_advanced(content: str) -> Dict[str, Any]:
    result = {
        "original": content,
        "decoded": content,
        "method_chain": [],
        "passwords_found": [],
        "layers": [],
        "is_encrypted": False,
        "cleaned": content
    }
    
    result["passwords_found"] = extract_passwords(content)
    cleaned = clean_corrupted_text(content)
    result["cleaned"] = cleaned
    
    decoders = [
        ("base64", decode_base64),
        ("hex", decode_hex),
        ("url", decode_url),
        ("rot13", decode_rot13),
        ("caesar", decode_caesar),
        ("xor", lambda t: decode_xor(t)),
        ("gzip", decode_gzip),
        ("zlib", decode_zlib),
        ("aes", lambda t: decode_aes(t)),
        ("rc4", lambda t: decode_rc4(t)),
        ("blowfish", lambda t: decode_blowfish(t)),
        ("des", lambda t: decode_des(t)),
        ("fernet", lambda t: decode_fernet(t))
    ]
    
    current = cleaned
    methods_used = []
    layers_history = [current]
    
    for attempt in range(15):
        best_result = current
        best_method = "none"
        best_score = 0
        
        for name, decoder in decoders:
            try:
                decoded = decoder(current)
                
                score = 0
                english_words = ['the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go', 'me', 'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know', 'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could', 'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come', 'its', 'over', 'think', 'also', 'back', 'after', 'use', 'two', 'how', 'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want', 'because', 'any', 'these', 'give', 'day', 'most', 'us']
                for word in english_words:
                    if word in decoded.lower():
                        score += 5
                
                if re.search(r'[\u0600-\u06FF]', decoded):
                    score += 10
                if re.search(r'[.!?]', decoded):
                    score += 3
                if len(decoded) > 20:
                    score += 2
                
                if score > best_score and decoded != current:
                    best_score = score
                    best_result = decoded
                    best_method = name
            except:
                pass
        
        if best_method != "none" and best_result != current:
            current = best_result
            methods_used.append(best_method)
            layers_history.append(current)
            if best_score > 20:
                break
        else:
            break
    
    result["decoded"] = current
    result["method_chain"] = methods_used
    result["layers"] = layers_history
    result["is_encrypted"] = len(methods_used) > 0
    
    if not result["is_encrypted"] or len(current) < 10:
        result["decoded"] = cleaned
    
    return result

# ========== محرك تحليل الملفات ==========

APP_DETECTION_DB = {
    "vmess": {"name": "V2Ray / VMess", "type": "vpn", "keywords": ["vmess://", "vless://"], "patterns": [r'vmess://[A-Za-z0-9+/=]+', r'vless://[A-Za-z0-9+/=]+']},
    "shadowsocks": {"name": "Shadowsocks", "type": "vpn", "keywords": ["ss://", "ssr://"], "patterns": [r'ss://[A-Za-z0-9+/=]+', r'ssr://[A-Za-z0-9+/=]+']},
    "wireguard": {"name": "WireGuard", "type": "vpn", "keywords": ["wireguard", "[Interface]", "[Peer]"], "patterns": [r'PrivateKey\s*=', r'PublicKey\s*=']},
    "openvpn": {"name": "OpenVPN", "type": "vpn", "keywords": ["openvpn", "ovpn"], "patterns": [r'remote\s+[^\s]+\s+\d+']},
    "trojan": {"name": "Trojan", "type": "vpn", "keywords": ["trojan://"], "patterns": [r'trojan://[^@]+@[^:]+:\d+']},
    "ssh": {"name": "SSH Tunnel", "type": "ssh", "keywords": ["ssh://", "ssh -"], "patterns": [r'ssh://[^@]+@[^:]+:\d+']},
    "pgp": {"name": "PGP / GPG", "type": "encryption", "keywords": ["-----BEGIN PGP"], "patterns": [r'-----BEGIN PGP MESSAGE-----']},
    "zip": {"name": "ZIP Archive", "type": "archive", "keywords": ["PK"], "patterns": [r'^PK\x03\x04']},
    "json": {"name": "JSON", "type": "data", "keywords": ["{", "["], "patterns": [r'^\s*\{', r'^\s*\[']},
    "xml": {"name": "XML", "type": "data", "keywords": ["<?xml"], "patterns": [r'<\?xml']},
    "yaml": {"name": "YAML", "type": "data", "keywords": ["---", ":"], "patterns": [r'^---', r'^[a-zA-Z][a-zA-Z0-9_]*:']}
}

def detect_file_type(content: str) -> Dict[str, Any]:
    result = {"detected_apps": [], "best_match": None, "confidence": 0, "extracted_info": {}}
    for app_name, app_data in APP_DETECTION_DB.items():
        score = 0
        for keyword in app_data.get("keywords", []):
            if keyword in content:
                score += 10
        for pattern in app_data.get("patterns", []):
            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                score += 5
        if score > 0:
            result["detected_apps"].append({"app": app_name, "name": app_data["name"], "type": app_data["type"], "score": score})
    result["detected_apps"].sort(key=lambda x: x["score"], reverse=True)
    if result["detected_apps"]:
        result["best_match"] = result["detected_apps"][0]
        result["confidence"] = min(result["detected_apps"][0]["score"] * 10, 100)
    return result

# ========== بوت الترحيب والفلترة ==========

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE, reason: str):
    user = update.message.from_user
    chat_id = update.effective_chat.id
    user_id = user.id
    warnings[user_id] += 1
    count = warnings[user_id]
    safe_name = html.escape(user.full_name)

    if count >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await context.bot.unban_chat_member(chat_id, user_id)
            msg = await update.message.reply_text(f"⛔️ <b>تم طرد</b> {safe_name}\nالسبب: وصل 3 انذارات", parse_mode="HTML")
            warnings[user_id] = 0
        except: msg = await update.message.reply_text("❌ ما عندي صلاحية طرد")
    elif count == 2:
        msg = await update.message.reply_text(f"⚠️ <b>انذار 2/3</b> اخر انذار\n{reason}", parse_mode="HTML")
    else:
        msg = await update.message.reply_text(f"⚠️ <b>انذار 1/3</b>\n{reason}", parse_mode="HTML")
    await asyncio.sleep(5)
    await msg.delete()

async def filter_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    if update.effective_user.id == OWNER_ID: return
    text = update.message.text.lower()

    if DELETE_LINKS and re.search(r'(http[s]?://\S+|t\.me/\S+|@\w+)', text, re.IGNORECASE):
        await update.message.delete()
        await warn_user(update, context, "السبب: نشر رابط")
        return

    for bad_word in GROUP_SETTINGS["bad_words"]:
        if bad_word in text:
            await update.message.delete()
            await warn_user(update, context, "السبب: كلمات مسيئة")
            return

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
            f"نورتنا ❤️ التزم بالقوانين"
        )
        keyboard = [
            [InlineKeyboardButton("👨‍💻 المطور", url="https://t.me/MRDPY")],
            [InlineKeyboardButton(f"📢 {group_title}", url=f"https://t.me/{group_username}")] if group_username else []
        ]
        keyboard = [row for row in keyboard if row]

        try:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=GROUP_SETTINGS["welcome_img"], caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except: await update.message.reply_text(caption, parse_mode="HTML")

# ========== أوامر البوت ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("👑 I'm online. Send any file or text to analyze.")
        return
    await update.message.reply_text(
        "📂 **Ultimate Decryption Bot v5.0**\n\n"
        "**Features:**\n"
        "• 🔓 Decrypt ALL types (Base64, Hex, URL, Caesar, ROT13, XOR, AES, RC4, Blowfish, DES, Fernet)\n"
        "• 🔄 Sequential decryption (up to 15 layers)\n"
        "• 🧹 Clean corrupted/mangled text\n"
        "• 🔑 Extract passwords & keys automatically\n"
        "• 📊 Detect file type (VPN configs, archives, etc.)\n"
        "• 🛡️ Welcome & moderation system\n\n"
        "**Commands:**\n"
        "/setgroup - Activate group\n"
        "/analyze - Analyze text\n\n"
        "**Works in ANY chat.**",
        parse_mode="Markdown"
    )

async def setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ALLOWED_GROUPS
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Only owner.")
        return
    group_id = update.effective_chat.id
    ALLOWED_GROUPS[group_id] = True
    save_group_config(ALLOWED_GROUPS)
    await update.message.reply_text(f"✅ Group activated: `{group_id}`", parse_mode="Markdown")

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /analyze <text>")
        return
    text = ' '.join(context.args)
    await process_analyze(update, text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ALLOWED_GROUPS
    if not ALLOWED_GROUPS:
        ALLOWED_GROUPS = load_group_config()
    
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    if user_id != OWNER_ID:
        if chat_type in ["group", "supergroup"]:
            group_id = update.effective_chat.id
            if group_id not in ALLOWED_GROUPS:
                return
        elif chat_type != "private":
            return
    
    if update.message and update.message.from_user and update.message.from_user.is_bot:
        return
    
    if update.message and update.message.document:
        await handle_document(update, context)
        return
    
    if update.message and update.message.text and not update.message.text.startswith('/'):
        await process_analyze(update, update.message.text)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("⚠️ File too large (max 20MB).")
        return
    
    try:
        status_msg = await update.message.reply_text("⏳ Decrypting and analyzing file...")
        file = await context.bot.get_file(doc.file_id)
        file_path = f"/tmp/{doc.file_name}"
        await file.download_to_drive(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'rb') as f:
                content = f.read().hex()
        except:
            content = "Binary file"
        
        os.remove(file_path)
        await process_analyze(update, content, doc.file_name)
        await status_msg.delete()
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {str(e)}")

async def process_analyze(update: Update, text: str, filename: str = "text_message"):
    try:
        status_msg = await update.message.reply_text("🔓 Decrypting all layers...")
        
        decoded_result = auto_decode_advanced(text)
        detection = detect_file_type(decoded_result["decoded"])
        
        report = f"📂 **Decryption Report**\n\n"
        report += f"📄 File: `{filename}`\n"
        report += f"📏 Original size: {len(text)} chars\n"
        report += f"📝 Decoded size: {len(decoded_result['decoded'])} chars\n\n"
        
        if decoded_result["is_encrypted"]:
            report += f"🔓 **Decryption chain:** {' → '.join(decoded_result['method_chain'])}\n"
            report += f"📊 Layers decoded: {len(decoded_result['method_chain'])}\n\n"
        else:
            report += "✅ **No encryption detected** (or already decoded)\n\n"
        
        if decoded_result["passwords_found"]:
            report += f"🔑 **Extracted passwords/keys:**\n"
            for pwd in decoded_result["passwords_found"][:10]:
                report += f"• `{pwd}`\n"
            if len(decoded_result["passwords_found"]) > 10:
                report += f"• ... and {len(decoded_result['passwords_found']) - 10} more\n"
            report += "\n"
        
        if detection["best_match"]:
            report += f"🔍 **Detected type:** {detection['best_match']['name']}\n"
            report += f"📊 Confidence: {detection['confidence']}%\n"
            report += f"🏷️ Category: {detection['best_match']['type']}\n\n"
        else:
            report += "❓ **Unknown file type**\n\n"
        
        preview = decoded_result["decoded"][:1500]
        if len(decoded_result["decoded"]) > 1500:
            preview += "...\n\n[Content truncated]"
        report += f"📄 **Decoded content preview:**\n```\n{preview}\n```\n"
        
        keyboard = [
            [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/MRDPY")],
            [InlineKeyboardButton("📢 Channel", url="https://t.me/X_X_SUDAN_DEV")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if len(report) > 4096:
            for i in range(0, len(report), 4000):
                await update.message.reply_text(report[i:i+4000], parse_mode="Markdown")
        else:
            await update.message.reply_text(report, parse_mode="Markdown", reply_markup=reply_markup)
        
        if decoded_result["decoded"] != text:
            decoded_file = f"decrypted_{int(time.time())}.txt"
            with open(decoded_file, 'w', encoding='utf-8') as f:
                f.write(decoded_result["decoded"])
            with open(decoded_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"decrypted_{filename.replace(' ', '_')[:30]}.txt",
                    caption="📄 Fully decrypted content"
                )
            os.remove(decoded_file)
        
        await status_msg.delete()
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error during decryption: {str(e)}")

def main():
    global ALLOWED_GROUPS
    ALLOWED_GROUPS = load_group_config()
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setgroup", setgroup))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, filter_messages))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    logger.info("🚀 Ultimate Decryption Bot v5.0 is running!")
    logger.info(f"📊 Crypto available: AES={CRYPTO_AVAILABLE}, Fernet={CRYPTOGRAPHY_AVAILABLE}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
