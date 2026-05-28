#!/usr/bin/env python3
"""
📚 PDF Bibliothek Bot
— Admins: PDFs kategorisieren, verwalten, verschieben, löschen
— Normale Mitglieder: nur browsen & suchen
— Läuft 24/7 auf Railway (kein Terminal nötig)
"""

import os, sqlite3, logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler,
    filters, ContextTypes
)

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
DB         = os.environ.get("DB_PATH", "bibliothek.db")
ADDING_CAT = 1

# ── Datenbank ─────────────────────────────────────────────────────────────────

def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS categories (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pdfs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id    TEXT NOT NULL UNIQUE,
                filename   TEXT NOT NULL,
                category   TEXT NOT NULL DEFAULT 'Unsorted',
                added_by   TEXT,
                date_added TEXT NOT NULL
            );
            INSERT OR IGNORE INTO categories (name) VALUES
                ('Unsorted'),
                ('Teachings'),
                ('Marriage & Counseling'),
                ('Servanthood'),
                ('Theology'),
                ('Bible & Exegesis'),
                ('Prayer'),
                ('Biography'),
                ('Series & Books'),
                ('Stories'),
                ('Worship & Devotional'),
                ('Youth & Children'),
                ('Missions & Evangelism');
        """)

def db(sql, params=(), fetch=None):
    with sqlite3.connect(DB) as conn:
        cur = conn.execute(sql, params)
        if fetch == "one": return cur.fetchone()
        if fetch == "all": return cur.fetchall()

def get_cats():
    return [r[0] for r in db("SELECT name FROM categories ORDER BY name", fetch="all")]

def add_cat(n):
    try:    db("INSERT INTO categories (name) VALUES (?)", (n,)); return True
    except: return False

def del_cat(n):
    count = db("SELECT COUNT(*) FROM pdfs WHERE category=?", (n,), fetch="one")[0]
    db("UPDATE pdfs SET category='Unsorted' WHERE category=?", (n,))
    db("DELETE FROM categories WHERE name=?", (n,))
    return count

def save_pdf(file_id, filename, category, added_by):
    try:
        db("INSERT INTO pdfs (file_id,filename,category,added_by,date_added) VALUES (?,?,?,?,?)",
           (file_id, filename, category, added_by, datetime.now().strftime("%d.%m.%Y %H:%M")))
        return True
    except sqlite3.IntegrityError:
        return False

def get_pdfs(cat, offset=0, limit=8):
    rows  = db("SELECT id,filename FROM pdfs WHERE category=? ORDER BY filename LIMIT ? OFFSET ?",
               (cat, limit, offset), fetch="all")
    total = db("SELECT COUNT(*) FROM pdfs WHERE category=?", (cat,), fetch="one")[0]
    return rows, total

def get_pdf(pid):
    return db("SELECT file_id,filename,category,added_by,date_added FROM pdfs WHERE id=?",
              (pid,), fetch="one")

def del_pdf(pid):
    r = db("SELECT filename FROM pdfs WHERE id=?", (pid,), fetch="one")
    db("DELETE FROM pdfs WHERE id=?", (pid,))
    return r[0] if r else None

def move_pdf(pid, cat):
    db("UPDATE pdfs SET category=? WHERE id=?", (cat, pid))

def search_pdfs(q):
    return db("SELECT id,filename,category FROM pdfs WHERE filename LIKE ? ORDER BY filename LIMIT 20",
              (f"%{q}%",), fetch="all")

def stats():
    total = db("SELECT COUNT(*) FROM pdfs", fetch="one")[0]
    cats  = db("SELECT category, COUNT(*) FROM pdfs GROUP BY category ORDER BY COUNT(*) DESC", fetch="all")
    return total, cats

# ── Rollen-Check ──────────────────────────────────────────────────────────────

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Prüft ob der User Admin in der Gruppe ist."""
    user_id = update.effective_user.id
    # Im privaten Chat mit dem Bot → immer Admin-Zugriff
    if update.effective_chat.type == "private":
        return True
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except:
        return False

async def is_admin_by_query(query, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    if query.message.chat.type == "private":
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except:
        return False

# ── Keyboards ─────────────────────────────────────────────────────────────────

def kb_main(admin=False):
    rows = [
        [InlineKeyboardButton("📚 Library",    callback_data="lib"),
         InlineKeyboardButton("🔍 Search",      callback_data="search_prompt")],
        [InlineKeyboardButton("📊 Statistics",  callback_data="stats")],
    ]
    if admin:
        rows.append([InlineKeyboardButton("⚙️ Manage Categories", callback_data="manage")])
    return InlineKeyboardMarkup(rows)

def kb_cats(prefix, extra=None, back="main"):
    rows = [[InlineKeyboardButton(f"📁 {c}", callback_data=f"{prefix}{c}")] for c in get_cats()]
    if extra: rows += extra
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=back)])
    return InlineKeyboardMarkup(rows)

def kb_back(target="main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=target)]])

# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    admin = await is_admin(u, c)
    total, _ = stats()
    role_text = "👑 *Admin access*" if admin else "👤 *Member access* — browse & search only"
    await u.message.reply_text(
        f"📚 *PDF Library*\n\n"
        f"{total} PDFs saved · {role_text}\n\n"
        "📌 *How it works:*\n"
        "• Send a PDF in the group → select category\n"
        "• `/library` — browse all PDFs\n"
        "• `/search keyword` — find by filename",
        parse_mode="Markdown", reply_markup=kb_main(admin)
    )

async def cb_main(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    admin = await is_admin_by_query(q, c)
    total, _ = stats()
    await q.edit_message_text(
        f"📚 *PDF Library* — {total} PDFs saved",
        parse_mode="Markdown", reply_markup=kb_main(admin)
    )

# ── PDF empfangen (nur Admins kategorisieren) ─────────────────────────────────

async def handle_pdf(u: Update, c: ContextTypes.DEFAULT_TYPE):
    doc = u.message.document
    if not doc or doc.mime_type != "application/pdf":
        return

    admin = await is_admin(u, c)
    if not admin:
        # Normale Mitglieder: nur Info-Nachricht
        await u.message.reply_text(
            "📄 New PDF detected! An admin will categorize it shortly.",
            reply_to_message_id=u.message.message_id
        )
        return

    sender = u.effective_user.first_name or "Unknown"
    c.user_data["pdf"] = {
        "file_id":  doc.file_id,
        "filename": doc.file_name or "Unknown.pdf",
        "added_by": sender,
    }

    kb = kb_cats("cat_set_", extra=[
        [InlineKeyboardButton("➕ New Category", callback_data="new_cat_pdf")]
    ], back="cancel_pdf")

    await u.message.reply_text(
        f"📄 *{doc.file_name}*\n\nWhich category?",
        parse_mode="Markdown", reply_markup=kb,
        reply_to_message_id=u.message.message_id
    )

async def cb_set_cat(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not await is_admin_by_query(q, c):
        await q.answer("⛔ Admins only.", show_alert=True); return
    await q.answer()
    cat = q.data.removeprefix("cat_set_")
    pdf = c.user_data.pop("pdf", None)
    if not pdf:
        await q.edit_message_text("❌ Session expired. Send the PDF again."); return
    ok = save_pdf(**pdf, category=cat)
    if ok:
        await q.edit_message_text(f"✅ *{pdf['filename']}*\n📁 Saved in: *{cat}*", parse_mode="Markdown")
    else:
        await q.edit_message_text(f"ℹ️ *{pdf['filename']}* is already in the library.", parse_mode="Markdown")

async def cb_cancel_pdf(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    c.user_data.pop("pdf", None)
    await q.delete_message()

# ── Library browsen (alle können) ────────────────────────────────────────────

async def cmd_library(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("📚 *Library — Choose a category:*",
                                parse_mode="Markdown", reply_markup=kb_cats("browse_"))

async def cb_lib(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    await q.edit_message_text("📚 *Library — Choose a category:*",
                               parse_mode="Markdown", reply_markup=kb_cats("browse_"))

async def cb_browse(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    raw   = q.data.removeprefix("browse_")
    parts = raw.rsplit("__p", 1)
    cat   = parts[0]
    page  = int(parts[1]) if len(parts) > 1 else 0
    pdfs, total = get_pdfs(cat, page * 8)
    pages = max(1, (total + 7) // 8)

    rows = [[InlineKeyboardButton(f"📄 {fn[:44]}", callback_data=f"pdf_{pid}")]
            for pid, fn in pdfs]
    nav = []
    if page > 0:         nav.append(InlineKeyboardButton("◀️", callback_data=f"browse_{cat}__p{page-1}"))
    if page+1 < pages:   nav.append(InlineKeyboardButton("▶️", callback_data=f"browse_{cat}__p{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Categories", callback_data="lib")])

    await q.edit_message_text(
        f"📁 *{cat}*  ·  {total} PDFs  ·  Page {page+1}/{pages}",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows)
    )

# ── PDF Detail ────────────────────────────────────────────────────────────────

async def cb_pdf(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    admin = await is_admin_by_query(q, c)
    pid   = int(q.data.removeprefix("pdf_"))
    pdf   = get_pdf(pid)
    if not pdf:
        await q.edit_message_text("❌ Not found."); return
    file_id, filename, cat, added_by, date = pdf

    # Admins sehen mehr Optionen
    if admin:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download",   callback_data=f"dl_{pid}"),
             InlineKeyboardButton("✏️ Move",        callback_data=f"mv_{pid}")],
            [InlineKeyboardButton("🗑️ Remove",      callback_data=f"del_ask_{pid}"),
             InlineKeyboardButton("⬅️ Back",        callback_data=f"browse_{cat}")],
        ])
    else:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download",   callback_data=f"dl_{pid}"),
             InlineKeyboardButton("⬅️ Back",        callback_data=f"browse_{cat}")],
        ])

    await q.edit_message_text(
        f"📄 *{filename}*\n📁 {cat}\n👤 {added_by or '–'}\n🕐 {date}",
        parse_mode="Markdown", reply_markup=kb
    )

async def cb_dl(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer("Sending…")
    pid = int(q.data.removeprefix("dl_"))
    pdf = get_pdf(pid)
    if pdf:
        await q.message.reply_document(document=pdf[0], caption=f"📄 {pdf[1]}\n📁 {pdf[2]}")

async def cb_del_ask(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not await is_admin_by_query(q, c):
        await q.answer("⛔ Admins only.", show_alert=True); return
    await q.answer()
    pid = int(q.data.removeprefix("del_ask_"))
    pdf = get_pdf(pid)
    await q.edit_message_text(
        f"🗑️ Remove *{pdf[1]}* from library?", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, remove", callback_data=f"del_yes_{pid}"),
             InlineKeyboardButton("❌ Cancel",       callback_data=f"pdf_{pid}")],
        ])
    )

async def cb_del_yes(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not await is_admin_by_query(q, c):
        await q.answer("⛔ Admins only.", show_alert=True); return
    await q.answer()
    pid  = int(q.data.removeprefix("del_yes_"))
    name = del_pdf(pid)
    await q.edit_message_text(f"🗑️ *{name}* removed.", parse_mode="Markdown",
                               reply_markup=kb_back("lib"))

async def cb_mv(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not await is_admin_by_query(q, c):
        await q.answer("⛔ Admins only.", show_alert=True); return
    await q.answer()
    pid  = int(q.data.removeprefix("mv_"))
    pdf  = get_pdf(pid)
    cats = [cat for cat in get_cats() if cat != pdf[2]]
    rows = [[InlineKeyboardButton(f"📁 {cat}", callback_data=f"mv_to_{pid}__{cat}")] for cat in cats]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data=f"pdf_{pid}")])
    await q.edit_message_text(f"✏️ Move *{pdf[1]}* to:",
                               parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def cb_mv_to(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    raw = q.data.removeprefix("mv_to_")
    pid_str, new_cat = raw.split("__", 1)
    move_pdf(int(pid_str), new_cat)
    pdf = get_pdf(int(pid_str))
    await q.edit_message_text(f"✅ *{pdf[1]}*\n📁 Moved to: *{new_cat}*",
                               parse_mode="Markdown", reply_markup=kb_back(f"browse_{new_cat}"))

# ── Suche (alle können) ───────────────────────────────────────────────────────

async def cmd_search(u: Update, c: ContextTypes.DEFAULT_TYPE):
    if not c.args:
        await u.message.reply_text("Usage: `/search keyword`", parse_mode="Markdown"); return
    results = search_pdfs(" ".join(c.args))
    if not results:
        await u.message.reply_text("❌ No PDFs found."); return
    rows = [[InlineKeyboardButton(f"📄 {fn[:38]} [{cat}]", callback_data=f"pdf_{pid}")]
            for pid, fn, cat in results]
    await u.message.reply_text(f"🔍 *{len(results)} result(s):*",
                                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def cb_search_prompt(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    await q.edit_message_text("🔍 Send me a search keyword:")

# ── Statistik (alle können) ───────────────────────────────────────────────────

async def cb_stats(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    total, cats = stats()
    lines = [f"📊 *Library Statistics*\n\n📚 Total: *{total} PDFs*\n"]
    for cat, n in cats:
        bar = "█" * min(max(n * 12 // max(total, 1), 1), 12)
        lines.append(f"📁 {cat}: *{n}*  {bar}")
    await q.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb_back())

# ── Kategorien verwalten (nur Admins) ─────────────────────────────────────────

async def cb_manage(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not await is_admin_by_query(q, c):
        await q.answer("⛔ Admins only.", show_alert=True); return
    await q.answer()
    await q.edit_message_text("⚙️ *Manage Categories:*", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ New Category",     callback_data="cat_new")],
            [InlineKeyboardButton("🗑️ Delete Category",  callback_data="cat_del_list")],
            [InlineKeyboardButton("⬅️ Back",             callback_data="main")],
        ]))

async def cb_cat_new_prompt(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not await is_admin_by_query(q, c):
        await q.answer("⛔ Admins only.", show_alert=True); return
    await q.answer()
    c.user_data["add_cat_ctx"] = "manage"
    await q.edit_message_text("➕ Type the name of the new category:")
    return ADDING_CAT

async def cb_new_cat_pdf(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not await is_admin_by_query(q, c):
        await q.answer("⛔ Admins only.", show_alert=True); return
    await q.answer()
    c.user_data["add_cat_ctx"] = "pdf"
    await q.edit_message_text("➕ Type the name of the new category:")
    return ADDING_CAT

async def handle_new_cat_text(u: Update, c: ContextTypes.DEFAULT_TYPE):
    name = u.message.text.strip()
    ctx  = c.user_data.pop("add_cat_ctx", "manage")
    if add_cat(name):
        msg = f"✅ Category *{name}* created!"
        if ctx == "pdf" and "pdf" in c.user_data:
            pdf = c.user_data.pop("pdf")
            save_pdf(**pdf, category=name)
            msg += f"\n📄 *{pdf['filename']}* saved in it."
        await u.message.reply_text(msg, parse_mode="Markdown")
    else:
        await u.message.reply_text(f"⚠️ *{name}* already exists.", parse_mode="Markdown")
    return ConversationHandler.END

async def cb_cat_del_list(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not await is_admin_by_query(q, c):
        await q.answer("⛔ Admins only.", show_alert=True); return
    await q.answer()
    cats = [cat for cat in get_cats() if cat != "Unsorted"]
    rows = [[InlineKeyboardButton(f"🗑️ {cat}", callback_data=f"cat_del_ask_{cat}")] for cat in cats]
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="manage")])
    await q.edit_message_text("Which category to delete?\n_PDFs will move to Unsorted._",
                               parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

async def cb_cat_del_ask(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    cat = q.data.removeprefix("cat_del_ask_")
    await q.edit_message_text(f"🗑️ Delete category *{cat}*?", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes",  callback_data=f"cat_del_yes_{cat}"),
             InlineKeyboardButton("❌ No",   callback_data="cat_del_list")],
        ]))

async def cb_cat_del_yes(u: Update, c: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query
    if not await is_admin_by_query(q, c):
        await q.answer("⛔ Admins only.", show_alert=True); return
    await q.answer()
    cat   = q.data.removeprefix("cat_del_yes_")
    moved = del_cat(cat)
    await q.edit_message_text(
        f"✅ *{cat}* deleted. {moved} PDF(s) moved to *Unsorted*.",
        parse_mode="Markdown", reply_markup=kb_back("manage"))

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    init_db()
    token = os.environ.get("TELEGRAM_TOKEN") or input("Bot token: ").strip()

    app = Application.builder().token(token).build()

    new_cat_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_cat_new_prompt, pattern=r"^cat_new$"),
            CallbackQueryHandler(cb_new_cat_pdf,    pattern=r"^new_cat_pdf$"),
        ],
        states={ADDING_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_cat_text)]},
        fallbacks=[CommandHandler("start", cmd_start)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("library", cmd_library))
    app.add_handler(CommandHandler("search",  cmd_search))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.add_handler(new_cat_conv)

    for pat, fn in [
        (r"^cat_set_",       cb_set_cat),
        (r"^cancel_pdf$",    cb_cancel_pdf),
        (r"^main$",          cb_main),
        (r"^lib$",           cb_lib),
        (r"^browse_",        cb_browse),
        (r"^pdf_\d+$",       cb_pdf),
        (r"^dl_\d+$",        cb_dl),
        (r"^del_ask_\d+$",   cb_del_ask),
        (r"^del_yes_\d+$",   cb_del_yes),
        (r"^mv_\d+$",        cb_mv),
        (r"^mv_to_",         cb_mv_to),
        (r"^search_prompt$", cb_search_prompt),
        (r"^stats$",         cb_stats),
        (r"^manage$",        cb_manage),
        (r"^cat_del_list$",  cb_cat_del_list),
        (r"^cat_del_ask_",   cb_cat_del_ask),
        (r"^cat_del_yes_",   cb_cat_del_yes),
    ]:
        app.add_handler(CallbackQueryHandler(fn, pattern=pat))

    print("✅ Bot is running!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
