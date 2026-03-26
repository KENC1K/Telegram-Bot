import os
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
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

if not all([TOKEN, ADMIN_CHAT_ID, FOLDER_ID]):
    raise ValueError("❌ Variabilele de mediu nu sunt setate corect!")

# -------------------- STATES --------------------
NAME, EMAIL, PHONE, SERVICE, DETAILS, DATA = range(6)

# -------------------- GOOGLE DRIVE --------------------
def setup_drive():
    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
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

# -------------------- STOP (IN LOC DE CANCEL) --------------------
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Conversație oprită.")
    context.user_data.clear()
    return ConversationHandler.END

# -------------------- START --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Start", callback_data="user_start")],
        [InlineKeyboardButton("❌ Stop", callback_data="stop")]
    ]
    await update.message.reply_text(
        "Salut! 👋 Apasă Start ca să începem.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Cum se numește afacerea ta?")
    return NAME

# -------------------- FLOW --------------------
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text("Email?")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text
    await update.message.reply_text("Telefon? (/skip)")
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
        [InlineKeyboardButton("Analiză + plan", callback_data="plan")],
        [InlineKeyboardButton("❌ Stop", callback_data="stop")]
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

    keyboard = [
        [InlineKeyboardButton("Continuă", callback_data="continue")],
        [InlineKeyboardButton("❌ Stop", callback_data="stop")]
    ]

    await query.edit_message_text(
        "Apasă continuă ca să trimiți date.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DETAILS

async def handle_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "continue":
        await query.edit_message_text(
            "Trimite datele (text / poze / documente)."
        )
        return DATA

# -------------------- DATA --------------------
async def collect_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    session = context.user_data.get("session")
    if not session:
        session = datetime.now().strftime("%Y-%m-%d_%H-%M")
        context.user_data["session"] = session

    session_folder = f"./Data/Clients/user_{user_id}_{session}"
    os.makedirs(session_folder, exist_ok=True)

    context.user_data["session_folder"] = session_folder

    if not context.user_data.get("info_saved"):
        with open(f"{session_folder}/info.txt", "w", encoding="utf-8") as f:
            f.write(f"Nume: {context.user_data.get('name')}\n")
            f.write(f"Email: {context.user_data.get('email')}\n")
            f.write(f"Telefon: {context.user_data.get('phone')}\n")
        context.user_data["info_saved"] = True

    if update.message.text:
        with open(f"{session_folder}/data.txt", "a", encoding="utf-8") as f:
            f.write(update.message.text + "\n")

    await update.message.reply_text(
        "Salvat ✅ mai trimiți?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Trimite mai mult", callback_data="more")],
            [InlineKeyboardButton("Finalizează", callback_data="done")],
            [InlineKeyboardButton("❌ Stop", callback_data="stop")]
        ])
    )
    return DATA

async def data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "more":
        await query.edit_message_text("Trimite în continuare.")
        return DATA

    await query.edit_message_text("Se încarcă...")

    session_folder = context.user_data.get("session_folder")

    if session_folder and os.path.isdir(session_folder):
        for file in os.listdir(session_folder):
            upload_to_drive(f"{session_folder}/{file}", file)

    await query.edit_message_text("Gata! Procesarea durează 2–5 zile.")
    return ConversationHandler.END

# -------------------- MAIN --------------------
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
                CallbackQueryHandler(data_callback, pattern="^(more|done)$")
            ]
        },
        fallbacks=[CallbackQueryHandler(stop, pattern="^stop$")]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    print("Bot pornit...")
    app.run_polling()

if __name__ == "__main__":
    main()
