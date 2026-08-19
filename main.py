from flask import Flask, render_template_string, request, redirect, session, send_from_directory
import json, os, time, threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters, ContextTypes

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'shabah_secret_2026') # مهم للاستضافة

BOT_TOKEN = os.environ.get('BOT_TOKEN', "8700746570:AAHJy6ypz3GbCZxDc_9pdtN-dWdQBJ7DiHc") # خليتو متغير بيئة
ADMIN_ID = int(os.environ.get('ADMIN_ID', "7093004518"))

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DATA_FILE = 'data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return {"apps": [], "groups": [], "images": []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)

HTML = '''<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>♕ 𝗧𝗲𝗮𝗺 𝗔𝗹-𝗦𝗵𝗮𝗯𝗮𝗵 𝗦𝗨𝗗𝗔𝗡𝗜 ♕</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700;900&display=swap');
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#0a0a0f;color:#e0e0e0;font-family:'Tajawal',sans-serif;overflow-x:hidden}
#bgCanvas{position:fixed;top:0;left:0;width:100%;height:100%;z-index:-1}
.site-title{text-align:center;padding:40px 20px 20px;position:relative;z-index:1}
.site-name{font-size:36px;font-weight:900;background:linear-gradient(90deg,#ff0066,#ffcc00,#00ccff,#33ff99,#ff0066);background-size:400% 400%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:rgb 3s ease infinite;letter-spacing:4px}
@keyframes rgb{0%{background-position:0% 50%;}50%{background-position:100% 50%;}100%{background-position:0% 50%;}}
.section{max-width:1200px;margin:50px auto;padding:0 20px;position:relative;z-index:1}
.section-title{text-align:center;font-size:28px;font-weight:900;color:#00ff88;margin-bottom:30px;border-bottom:2px solid #00ff88;padding-bottom:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:25px}
.card{background:rgba(20,20,30,0.85);border:2px solid rgba(255,255,255,0.1);border-radius:16px;overflow:hidden;text-align:center;backdrop-filter:blur(10px);transition:0.3s}
.card:hover{transform:translateY(-5px);border-color:#8B5CF6;box-shadow:0 0 20px rgba(139,92,246,0.3)}
.card img{width:100%;height:200px;object-fit:contain;background:#111}
.card-body{padding:20px}
.app-name{font-size:18px;font-weight:700;color:#fff;margin-bottom:12px}
.download-btn{display:block;background:linear-gradient(90deg,#8B5CF6,#A855F7);color:#fff;text-align:center;padding:12px;border-radius:10px;text-decoration:none;font-weight:700;transition:0.3s}
.download-btn:hover{opacity:0.8;transform:scale(1.05)}
.groups{display:flex;flex-direction:column;gap:15px;max-width:600px;margin:0 auto}
.group-btn{display:flex;align-items:center;gap:15px;background:linear-gradient(90deg,rgba(37,211,102,0.15),rgba(37,211,102,0.05));border:2px solid #25D366;border-radius:50px;padding:15px 25px;text-decoration:none;transition:0.3s;backdrop-filter:blur(10px)}
.group-btn:hover{background:linear-gradient(90deg,#25D366,#20BA5A);transform:scale(1.02);box-shadow:0 0 25px rgba(37,211,102,0.4)}
.group-icon{width:50px;height:50px;background:#25D366;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.group-info{display:flex;flex-direction:column;text-align:right;flex:1}
.group-name{color:#fff;font-size:18px;font-weight:700;margin-bottom:3px}
.group-link{color:#aaa;font-size:12px;direction:ltr;text-align:left}
.img-grid img{width:100%;height:250px;object-fit:cover;border-radius:12px;cursor:pointer;transition:0.3s;border:2px solid transparent}
.img-grid img:hover{transform:scale(1.05);border-color:#00ff88}
.empty{text-align:center;padding:40px;opacity:0.5;font-size:18px}
</style>
</head>
<body>
<canvas id="bgCanvas"></canvas>
<div class="site-title"><div class="site-name">♕ 𝗧𝗲𝗮𝗺 𝗔𝗹-𝗦𝗵𝗮𝗯𝗮𝗵 𝗦𝗨𝗗𝗔𝗡𝗜 ♕</div></div>
<div class="section"><div class="section-title">📱 التطبيقات</div>{% if data.apps %}<div class="grid">{% for app in data.apps %}<div class="card"><img src="{{ url_for('uploaded_file', filename=app.logo) if app.logo else 'https://i.ibb.co/nR8mQmK/no-image.png' }}"><div class="card-body"><div class="app-name">{{ app.name }}</div><a class="download-btn" href="{{ url_for('uploaded_file', filename=app.file) }}" download>📥 تحميل</a></div></div>{% endfor %}</div>{% else %}<div class="empty">لا توجد تطبيقات بعد</div>{% endif %}</div>
<div class="section"><div class="section-title">💬 قروباتنا</div>{% if data.groups %}<div class="groups">{% for g in data.groups %}<a href="{{ g.link }}" target="_blank" class="group-btn"><div class="group-icon"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" fill="#fff" viewBox="0 0 16 16"><path d="M13.601 2.326A7.854 7.854 0 0 0 7.994 0C3.627 0 .068 3.558.064 7.926c0 1.399.366 2.76 1.057 3.965L0 16l4.204-1.102a7.933 7.933 0 0 0 3.79.965h.004c4.368 0 7.926-3.558 7.93-7.93A7.898 7.898 0 0 0 13.6 2.326zM7.994 14.521a6.573 6.573 0 0 1-3.356-.92l-.24-.144-2.494.654.666-2.433-.156-.251a6.56 6.56 0 0 1-1.007-3.505c0-3.626 2.957-6.584 6.591-6.584a6.56 6.56 0 0 1 4.66 1.931 6.557 6.557 0 0 1 1.928 4.66c-.004 3.639-2.961 6.592-6.592 6.592zm3.615-4.934c-.197-.099-1.17-.578-1.353-.646-.182-.065-.315-.099-.445.099-.133.197-.513.646-.627.775-.114.133-.232.148-.43.05-.197-.1-.836-.308-1.592-.985-.59-.525-.985-1.175-1.103-1.372-.114-.198-.011-.304.088-.403.087-.088.197-.232.296-.346.1-.114.133-.198.198-.33.065-.134.034-.248-.015-.347-.05-.099-.445-1.076-.612-1.47-.16-.389-.323-.335-.445-.34-.114-.007-.247-.007-.38-.007a.729.729 0 0 0-.529.247c-.182.198-.691.677-.691 1.654 0 .977.71 1.916.81 2.049.098.133 1.394 2.132 3.383 2.992.47.205.84.326 1.129.418.475.152.904.129 1.246.08.38-.058 1.171-.48 1.338-.943.164-.464.164-.86.114-.943-.049-.084-.182-.133-.38-.232z"/></svg></div><div class="group-info"><div class="group-name">{{ g.name if g.name else 'قروب واتساب' }}</div><div class="group-link">{{ g.link[:50] }}...</div></div></a>{% endfor %}</div>{% else %}<div class="empty">لا توجد قروبات بعد</div>{% endif %}</div>
<div class="section"><div class="section-title">🖼️ معرض الصور</div>{% if data.images %}<div class="grid img-grid">{% for img in data.images %}<img src="{{ url_for('uploaded_file', filename=img.file) }}" onclick="window.open(this.src)">{% endfor %}</div>{% else %}<div class="empty">لا توجد صور بعد</div>{% endif %}</div>
<script>const canvas=document.getElementById('bgCanvas');const ctx=canvas.getContext('2d');canvas.width=window.innerWidth;canvas.height=window.innerHeight;const dots=[];for(let i=0;i<100;i++){dots.push({x:Math.random()*canvas.width,y:Math.random()*canvas.height,r:Math.random()*3+1,dx:(Math.random()-0.5)*0.5,dy:(Math.random()-0.5)*0.5,hue:Math.random()*360})}function animate(){ctx.clearRect(0,0,canvas.width,canvas.height);dots.forEach(dot=>{dot.x+=dot.dx;dot.y+=dot.dy;dot.hue=(dot.hue+1)%360;if(dot.x<0||dot.x>canvas.width)dot.dx*=-1;if(dot.y<0||dot.y>canvas.height)dot.dy*=-1;ctx.beginPath();ctx.arc(dot.x,dot.y,dot.r,0,Math.PI*2);ctx.fillStyle=`hsl(${dot.hue},100%,50%)`;ctx.shadowBlur=15;ctx.shadowColor=`hsl(${dot.hue},100%,50%)`;ctx.fill()});requestAnimationFrame(animate)}animate();window.addEventListener('resize',()=>{canvas.width=window.innerWidth;canvas.height=window.innerHeight})</script>
</body></html>'''

ADMIN_HTML = '''<!DOCTYPE html><html dir="rtl"><head><meta charset="UTF-8"><title>لوحة التحكم</title>
<style>body{background:#0a0a0f;color:#e0e0e0;font-family:Tajawal;padding:20px}
h1{color:#00ff88;text-align:center;margin-bottom:30px}
.box{background:rgba(20,20,30,0.7);padding:20px;border-radius:12px;border:1px solid #333;margin:20px 0}
input,button{padding:12px;margin:5px;border-radius:8px;border:1px solid #444;background:#111;color:#fff;width:calc(100% - 22px)}
button{background:#00ff88;color:#000;font-weight:700;cursor:pointer;width:auto}
.item{border:1px solid #333;padding:10px;border-radius:8px;margin:10px 0;display:flex;justify-content:space-between;align-items:center}
</style></head><body>
<h1>♕ 𝗧𝗲𝗮𝗺 𝗔𝗹-𝗦𝗵𝗮𝗯𝗮𝗵 𝗦𝗨𝗗𝗔𝗡𝗜 ♕</h1>
<div class="box"><h3>📱 رفع تطبيق</h3><form method="post" enctype="multipart/form-data"><input type="hidden" name="action" value="add_app"><input name="app_name" placeholder="اسم التطبيق" required><input name="app_file" type="file" required><input name="app_logo" type="file" accept="image/*" required><button>رفع</button></form>{% for app in data.apps %}<div class="item"><span>{{ app.name }}</span><form method="post"><input type="hidden" name="action" value="delete_app"><input type="hidden" name="app_id" value="{{ app.id }}"><button style="background:#ff4444">حذف</button></form></div>{% endfor %}</div>
<div class="box"><h3>💬 اضافة قروب</h3><form method="post"><input type="hidden" name="action" value="add_group"><input name="group_name" placeholder="اسم القروب" required><input name="group_link" placeholder="رابط القروب" required><button>اضافة</button></form>{% for g in data.groups %}<div class="item"><span>{{ g.name }}</span><form method="post"><input type="hidden" name="action" value="delete_group"><input type="hidden" name="group_id" value="{{ g.id }}"><button style="background:#ff4444">حذف</button></form></div>{% endfor %}</div>
<div class="box"><h3>🖼️ رفع صورة</h3><form method="post" enctype="multipart/form-data"><input type="hidden" name="action" value="add_image"><input name="img_file" type="file" accept="image/*" required><button>رفع</button></form>{% for img in data.images %}<div class="item"><span>{{ img.file }}</span><form method="post"><input type="hidden" name="action" value="delete_image"><input type="hidden" name="img_id" value="{{ img.id }}"><button style="background:#ff4444">حذف</button></form></div>{% endfor %}</div>
<a href="/logout" style="color:#ff4444">تسجيل خروج</a></body></html>'''

LOGIN_HTML = '''<!DOCTYPE html><html dir="rtl"><head><meta charset="UTF-8"><title>دخول</title><style>body{background:#0a0a0f;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;font-family:Tajawal}.box{background:rgba(20,20,30,0.9);padding:40px;border-radius:20px;border:2px solid #00ff88;width:350px}input{width:100%;padding:14px;margin:10px 0;border-radius:10px;border:2px solid #333;background:#111;color:#fff}button{width:100%;padding:15px;background:#00ff88;color:#000;border:0;border-radius:10px;font-weight:700;font-size:16px}</style></head><body><div class="box"><h2 style="text-align:center;color:#00ff88">دخول الادمن</h2><form method="post"><input type="password" name="password" placeholder="كلمة السر: admin123" required><button>دخول</button></form></div></body></html>'''

@app.route('/')
def home(): return render_template_string(HTML, data=load_data())
@app.route('/uploads/<filename>')
def uploaded_file(filename): return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'):
        if request.method == 'POST' and request.form.get('password') == "admin123":
            session['admin'] = True; return redirect('/admin')
        return LOGIN_HTML
    data = load_data()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_app':
            f = request.files['app_file']; l = request.files['app_logo']
            f.save(os.path.join(UPLOAD_FOLDER, f.filename)); l.save(os.path.join(UPLOAD_FOLDER, l.filename))
            data['apps'].append({"id": str(int(time.time())),"name": request.form['app_name'],"file": f.filename,"logo": l.filename})
        if action == 'add_group':
            data['groups'].append({"id": str(int(time.time())),"name": request.form['group_name'],"link": request.form['group_link']})
        if action == 'add_image':
            img = request.files['img_file']; img.save(os.path.join(UPLOAD_FOLDER, img.filename))
            data['images'].append({"id": str(int(time.time())),"file": img.filename})
        if action == 'delete_app': data['apps'] = [a for a in data['apps'] if a['id']!= request.form['app_id']]
        if action == 'delete_group': data['groups'] = [g for g in data['groups'] if g['id']!= request.form['group_id']]
        if action == 'delete_image': data['images'] = [i for i in data['images'] if i['id']!= request.form['img_id']]
        save_data(data); return redirect('/admin')
    return render_template_string(ADMIN_HTML, data=data)
@app.route('/logout')
def logout(): session.pop('admin', None); return redirect('/gopmo')

# === البوت ===
telegram_app = Application.builder().token(BOT_TOKEN).build()
APP_NAME, APP_FILE, APP_LOGO, GRP_LINK, GRP_NAME, IMG_FILE = range(6)
temp = {}

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id != ADMIN_ID: 
        await u.message.reply_text("انت ما الادمن")
        return
    kb = [[InlineKeyboardButton("📱 رفع تطبيق", callback_data="app")],[InlineKeyboardButton("💬 اضافة قروب", callback_data="grp")],[InlineKeyboardButton("🖼️ رفع صورة", callback_data="img")]]
    await u.message.reply_text("♕ لوحة تحكم Team Al-Shabah ♕", reply_markup=InlineKeyboardMarkup(kb))

async def btn(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    if q.data=="app": await q.edit_message_text("الخطوة 1: ارسل اسم التطبيق"); return APP_NAME
    if q.data=="grp": await q.edit_message_text("الخطوة 1: ارسل رابط القروب"); return GRP_LINK
    if q.data=="img": await q.edit_message_text("ارسل الصورة"); return IMG_FILE

async def get_app_name(u: Update, c: ContextTypes.DEFAULT_TYPE): temp['name']=u.message.text; await u.message.reply_text("الخطوة 2: ارسل ملف apk"); return APP_FILE
async def get_app_file(u: Update, c: ContextTypes.DEFAULT_TYPE):
    f=await u.message.document.get_file(); path=f"uploads/{u.message.document.file_name}"; await f.download_to_drive(path); temp['file']=u.message.document.file_name
    await u.message.reply_text("الخطوة 3: ارسل صورة اللوغو"); return APP_LOGO
async def get_app_logo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    p=await u.message.photo[-1].get_file(); name=f"logo_{int(time.time())}.jpg"; path=f"uploads/{name}"; await p.download_to_drive(path)
    data=load_data(); data['apps'].append({"id":str(int(time.time())),"name":temp['name'],"file":temp['file'],"logo":name}); save_data(data)
    await u.message.reply_text("✅ تم رفع التطبيق"); return ConversationHandler.END

async def get_grp_link(u: Update, c: ContextTypes.DEFAULT_TYPE): temp['link']=u.message.text; await u.message.reply_text("الخطوة 2: ارسل اسم القروب"); return GRP_NAME
async def get_grp_name(u: Update, c: ContextTypes.DEFAULT_TYPE):
    data=load_data(); data['groups'].append({"id":str(int(time.time())),"name":u.message.text,"link":temp['link']}); save_data(data)
    await u.message.reply_text("✅ تم اضافة القروب"); return ConversationHandler.END

async def get_img(u: Update, c: ContextTypes.DEFAULT_TYPE):
    p=await u.message.photo[-1].get_file(); name=f"img_{int(time.time())}.jpg"; path=f"uploads/{name}"; await p.download_to_drive(path)
    data=load_data(); data['images'].append({"id":str(int(time.time())),"file":name}); save_data(data)
    await u.message.reply_text("✅ تم رفع الصورة"); return ConversationHandler.END

conv = ConversationHandler(entry_points=[CallbackQueryHandler(btn, per_message=True)], states={
    APP_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_app_name)],
    APP_FILE:[MessageHandler(filters.Document.ALL, get_app_file)],
    APP_LOGO:[MessageHandler(filters.PHOTO, get_app_logo)],
    GRP_LINK:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_grp_link)],
    GRP_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_grp_name)],
    IMG_FILE:[MessageHandler(filters.PHOTO, get_img)]
}, fallbacks=[], per_message=True)
telegram_app.add_handler(CommandHandler('start', start)); telegram_app.add_handler(conv)

def run_web():
    port = int(os.environ.get("PORT", 7000))
    app.run(host='0.0.0.0', port=port, debug=False)

def run_bot():
    print("البوت شغال...")
    telegram_app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()
