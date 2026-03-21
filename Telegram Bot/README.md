# FiloPing Telegram Bot

This is a Telegram bot that collects business information and allows users to submit data and documents for analysis.

## Features

- Step-by-step user interaction (name, email, phone number, service type).  
- Saves collected data locally in files and a CSV.  
- Supports sending text, photos, and documents.  
- Conversation flow managed with inline buttons and `/start` and `/cancel` commands.  

## Installation

1. Create a virtual environment and install dependencies:

```bash
python -m venv venv
# On Linux/macOS
source venv/bin/activate
# On Windows
venv\Scripts\activate

pip install -r requirements.txt
````

2. Open the `main.py` file and replace the placeholders with your actual bot token and admin chat ID:

```python
ADMIN_CHAT_ID = "your_admin_chat_id"
TOKEN = "your_telegram_bot_token"
```

## Configuration

* User data is saved locally in `E:/.../Data/Clients/` (you can change this path in the code).

## Usage

1. Start the bot:

```bash
python "main.py"
```

2. Open Telegram and send `/start` to the bot to begin the conversation.
3. The bot will guide users through submitting their information and saving it locally.
