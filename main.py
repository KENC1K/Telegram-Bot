import os
import csv
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, CallbackQueryHandler, filters
)
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# -------------------- SETTINGS --------------------
TOKEN = os.getenv("TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))
FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not all([TOKEN, ADMIN_CHAT_ID, FOLDER_ID, WEBHOOK_URL]):
    raise ValueError("❌ Lipsesc variabile de mediu!")

NAME, EMAIL, PHONE, SERVICE, DETAILS, DATA = range(6)

# -------------------- GOOGLE DRIVE --------------------
def setup_drive():
    creds = Credentials(
        token=None,
        refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN"),
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token"
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds)

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

# -------------------- HANDLERS --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Start", callback_data="user_start")]]
    await update.message.reply_text(
        "Salut! 👋\nApasă Start ca să începem analiza costurilor.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Cum se numește afacerea ta?")
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Email?")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text
    await update.message.reply_text("Telefon? (/skip dacă nu)")
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
    await update.message.reply_text("Alege tipul:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SERVICE

async def service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["service"] = query.data

    text = "Analiză simplă" if query.data == "simple" else "Analiză + plan detaliată"

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

    await query.edit_message_text("Trimite datele. Apasă 'Am terminat' când e gata.")
    return DATA

async def choose_service_from_callback(query):
    keyboard = [
        [InlineKeyboardButton("Analiză simplă", callback_data="simple")],
        [InlineKeyboardButton("Analiză + plan", callback_data="plan")]
    ]
    await query.edit_message_text("Alege tipul:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SERVICE

async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    session = context.user_data.get("session")

    if not session:
        session = datetime.now().strftime("%Y-%m-%d_%H-%M")
        context.user_data["session"] = session

    BASE = "/tmp"
    folder = os.path.join(BASE, f"user_{user_id}_{session}")
    os.makedirs(folder, exist_ok=True)
    context.user_data["folder"] = folder

    if not context.user_data.get("info_saved"):
        with open(os.path.join(folder, "info.txt"), "w") as f:
            f.write(str(context.user_data))
        context.user_data["info_saved"] = True

    if update.message.text:
        with open(os.path.join(folder, "data.txt"), "a") as f:
            f.write(update.message.text + "\n")

    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        path = os.path.join(folder, f"{time.time()}.jpg")
        await file.download_to_drive(path)

    if update.message.document:
        file = await update.message.document.get_file()
        path = os.path.join(folder, update.message.document.file_name)
        await file.download_to_drive(path)

    keyboard = [
        [InlineKeyboardButton("Mai trimit", callback_data="more")],
        [InlineKeyboardButton("Am terminat", callback_data="done")]
    ]

    await update.message.reply_text("Salvat ✔️", reply_markup=InlineKeyboardMarkup(keyboard))
    return DATA

async def data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "more":
        await query.edit_message_text("Trimite mai departe.")
        return DATA

    await query.edit_message_text("Upload pe Drive...")

    folder = context.user_data.get("folder")

    if folder:
        for file in os.listdir(folder):
            upload_to_drive(os.path.join(folder, file), file)

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"User {query.from_user.id} a trimis date"
    )

    save_csv(query.from_user.id, context)

    await query.edit_message_text("Gata ✅")
    return ConversationHandler.END

def save_csv(user_id, context):
    path = "/tmp/clients.csv"
    exists = os.path.isfile(path)

    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["user_id", "name", "email", "phone", "service"])

        writer.writerow([
            user_id,
            context.user_data.get("name"),
            context.user_data.get("email"),
            context.user_data.get("phone"),
            context.user_data.get("service")
        ])

    upload_to_drive(path, "clients.csv")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Anulat.")
    return ConversationHandler.END

# -------------------- MAIN --------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
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
    app.add_handler(conv)

    PORT = int(os.environ.get("PORT", 10000))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()
