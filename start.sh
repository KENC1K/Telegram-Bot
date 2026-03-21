#!/bin/bash
# Instalează dependențele
pip3 install --no-cache-dir -r "Telegram Bot/requirements.txt"

# Rulează botul
python3 "Telegram Bot/main.py"
