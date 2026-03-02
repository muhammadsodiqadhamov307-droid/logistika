#!/bin/bash

# Logs directory
mkdir -p logs

echo "Starting Odoo Server in background..."
# Start Odoo in the background, redirecting output to logs/odoo.log
# Using -c odoo.conf as standard for your server
python3 src/odoo-bin -c odoo.conf -d default "$@" > logs/odoo.log 2>&1 &
ODOO_PID=$!
echo $ODOO_PID > .odoo.pid

echo "Waiting Odoo to initialize (10s)..."
sleep 10

echo "Starting Telegram Bot in background..."
# Start the Telegram Bot in the background, redirecting output to logs/bot.log
python3 custom_addons/van_sales_pharma/telegram_bot.py > logs/bot.log 2>&1 &
BOT_PID=$!
echo $BOT_PID > .bot.pid

echo "------------------------------------------------"
echo "✅ Both processes are now running in the BACKGROUND."
echo "Odoo PID: $ODOO_PID"
echo "Bot PID: $BOT_PID"
echo "------------------------------------------------"
echo "To see Odoo logs: tail -f logs/odoo.log"
echo "To see Bot logs:  tail -f logs/bot.log"
echo "To stop them: kill $ODOO_PID $BOT_PID"
