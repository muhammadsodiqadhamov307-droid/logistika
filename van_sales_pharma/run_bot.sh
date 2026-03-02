#!/bin/bash

echo "Starting Odoo Server..."
# Start Odoo in the background
python src/odoo-bin -c odoo.conf -d default "$@" &
ODOO_PID=$!

echo "Waiting a few seconds for Odoo to start up..."
sleep 5

echo "Starting Telegram Bot..."
# Start the Telegram Bot in the background
python custom_addons/van_sales_pharma/telegram_bot.py &
BOT_PID=$!

echo "Both processes are running."
echo "Press Ctrl+C to stop both Odoo and the Telegram Bot."

# Trap Ctrl+C to stop both processes cleanly
trap "echo 'Stopping processes...'; kill $ODOO_PID; kill $BOT_PID; exit" SIGINT SIGTERM

# Wait indefinitely so the script doesn't exit
wait $ODOO_PID $BOT_PID
