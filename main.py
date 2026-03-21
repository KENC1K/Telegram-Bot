import os
import csv
import json
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, CallbackQueryHandler, filters
)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.service_account import Credentials

# -------------------- SETTINGS --------------------
TOKEN = os.getenv("TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER")

if not TOKEN or not ADMIN_CHAT_ID or not FOLDER_ID:
    raise ValueError("❌ TOKEN, ADMIN_CHAT_ID sau GOOGLE_DRIVE_FOLDER nu sunt setate!")

# States
NAME, EMAIL, PHONE, SERVICE, DETAILS, DATA = range(6)

# -------------------- GOOGLE DRIVE --------------------
def setup_drive():
    service_account_info = json.loads(os.getenv("SERVICE_ACCOUNT_JSON"))
    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    return build('drive', 'v3', credentials=creds)

drive_service = setup_drive()

def upload_to_drive(local_path, drive_filename):
    file_metadata = {"name": drive_filename, "parents": [FOLDER_ID]}
    media = MediaFileUpload(local_path)
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    return file.get("id")

# -------------------- BOT HANDLERS --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Start", callback_data="user_start")]]
    await update.message.reply_text(
        "Salut! 👋\nApasă Start ca să începem analiza costurilor.\nTotul este gratuit și sigur.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Perfect! Hai să începem.\n\nCum se numește afacerea ta?")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Care este email-ul tău?")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text
    await update.message.reply_text("Vrei să lași și un număr de telefon? (scrie sau /skip)")
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text
    return await choose_service(update, context)

async def skip_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = "N/A"
    return await choose_service(update, context)

async def choose_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Analiză simplă", callback_data="simple")],
        [InlineKeyboardButton("Analiză + plan", callback_data="plan")]
    ]
    await update.message.reply_text(
        "Alege tipul de analiză:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SERVICE

async def service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["service"] = query.data
    text = "Analiza simplă îți oferă o imagine rapidă." if query.data == "simple" else "Analiza + plan include pași concreți."
    keyboard = [
        [InlineKeyboardButton("Continuă", callback_data="continue")],
        [InlineKeyboardButton("Înapoi", callback_data="back")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return DETAILS

async def handle_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back":
        return await choose_service_from_callback(query)
    if query.data == "continue":
        await query.edit_message_text(
            "Trimite informații (poze, text, documente).\n\nCând ai terminat, apasă 'Am terminat'."
        )
        return DATA

async def choose_service_from_callback(query):
    keyboard = [
        [InlineKeyboardButton("Analiză simplă", callback_data="simple")],
        [InlineKeyboardButton("Analiză + plan", callback_data="plan")]
    ]
    await query.edit_message_text(
        "Alege tipul de analiză:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SERVICE

async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    session = context.user_data.get("session")
    if not session:
        session = datetime.now().strftime("%Y-%m-%d_%H-%M")
        context.user_data["session"] = session

    # Folder temporar local
    BASE_FOLDER = os.path.join(os.getenv("HOME", "."), "Data", "Clients")
    session_folder = os.path.join(BASE_FOLDER, f"user_{user_id}_{session}")
    os.makedirs(session_folder, exist_ok=True)

    # --------- Save info.txt ---------
    info_path = os.path.join(session_folder, "info.txt")
    with open(info_path, "w", encoding="utf-8") as f:
        f.write(f"Nume: {context.user_data.get('name')}\n")
        f.write(f"Email: {context.user_data.get('email')}\n")
        f.write(f"Telefon: {context.user_data.get('phone')}\n")
        f.write(f"Serviciu: {context.user_data.get('service')}\n")
    upload_to_drive(info_path, f"user_{user_id}_{session}_info.txt")

    # --------- Text ---------
    if update.message.text:
        data_txt_path = os.path.join(session_folder, "data.txt")
        with open(data_txt_path, "a", encoding="utf-8") as f:
            f.write(update.message.text + "\n")
        upload_to_drive(data_txt_path, f"user_{user_id}_{session}_data.txt")

    # --------- Photo ---------
    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        local_photo_path = os.path.join(session_folder, f"{user_id}_{int(time.time())}.jpg")
        await file.download_to_drive(local_photo_path)
        upload_to_drive(local_photo_path, f"user_{user_id}_{session}_photo.jpg")

    # --------- Document ---------
    if update.message.document:
        doc = update.message.document
        file = await doc.get_file()
        local_doc_path = os.path.join(session_folder, f"{user_id}_{int(time.time())}_{doc.file_name}")
        await file.download_to_drive(local_doc_path)
        upload_to_drive(local_doc_path, f"user_{user_id}_{session}_{doc.file_name}")

    await update.message.reply_text("Datele tale au fost salvate pe Drive ✅")

async def data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "more":
        await query.edit_message_text("Trimite următoarele date.")
        return DATA
    await query.edit_message_text("Mulțumim! 🙌")
    user_id = query.from_user.id
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"User {user_id} a trimis date.")
    save_to_csv(user_id, context)
    return ConversationHandler.END

# --------- CSV ---------
def save_to_csv(user_id, context):
    path = "/tmp/clients.csv"  # fișier temporar
    exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["user_id", "name", "email", "phone", "service", "date"])
        writer.writerow([
            user_id,
            context.user_data.get("name"),
            context.user_data.get("email"),
            context.user_data.get("phone"),
            context.user_data.get("service"),
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ])
    # Upload CSV central pe Drive
    upload_to_drive(path, "clients.csv")

# --------- CANCEL ---------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Anulat.")
    return ConversationHandler.END

# --------- MAIN ---------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_start_button, pattern="user_start")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone),
                CommandHandler("skip", skip_phone)
            ],
            SERVICE: [CallbackQueryHandler(service_details)],
            DETAILS: [CallbackQueryHandler(handle_details)],
            DATA: [
                MessageHandler(filters.ALL, collect_data),
                CallbackQueryHandler(data_callback, pattern="more|done")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
