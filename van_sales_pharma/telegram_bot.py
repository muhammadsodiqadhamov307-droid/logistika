import os
import sys
import logging
import configparser
import xmlrpc.client
from datetime import datetime

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

# Set up raw logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Basic Odoo Connection Setup 
# In a real environment, read these from environment variables or a config file
ODOO_URL = "https://logistics1234.duckdns.org"
ODOO_DB = "default"
ODOO_USER = "admin"  # Hardcoded per instructions for local script
ODOO_PASSWORD = "admin" # Adjust if your local db admin password is different

# State definitions for Registration Conversation
ASK_NAME, ASK_PHONE = range(2)

def get_odoo_models():
    """Authenticates and returns the xmlrpc models proxy, plus the uid"""
    try:
        common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
        uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
        if not uid:
            logger.error("Authentication to Odoo Failed.")
            return None, None
        models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
        return models, uid
    except Exception as e:
        logger.error(f"Odoo XML-RPC Error: {e}")
        return None, None

def get_bot_token():
    """Fetch the Token natively out of Odoo sys parameter via XML-RPC"""
    models, uid = get_odoo_models()
    if not models:
        return None
    records = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'ir.config_parameter', 'search_read', 
        [[('key', '=', 'van.telegram.bot.token')]], 
        {'fields': ['value'], 'limit': 1}
    )
    if records:
        return records[0].get('value')
    return None

def build_main_menu():
    keyboard = [
        [InlineKeyboardButton("💰 Balans (Qarz)", callback_data='menu_balans')],
        [InlineKeyboardButton("📋 Barcha tranzaksiyalar", callback_data='menu_tranzaksiyalar')],
        [InlineKeyboardButton("🧾 Savdo cheklari (Batafsil)", callback_data='menu_savdo_cheklari')]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- REGISTRATION CONVERSATION ---

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = str(update.effective_chat.id)
    models, uid = get_odoo_models()
    if not models:
        await update.message.reply_text("Tizim bilan bog'lanishda xatolik yuz berdi. Iltimos keyinroq urinib ko'ring.")
        return ConversationHandler.END

    # Check if client already exists by telegram_chat_id
    partner_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search', [[('telegram_chat_id', '=', chat_id)]])
    
    if partner_ids:
        # Already registered
        await update.message.reply_text(
            "Assalomu alaykum! Siz allaqachon ro'yxatdan o'tgansiz.\nQuyidagi menyudan foydalanishingiz mumkin:",
            reply_markup=build_main_menu()
        )
        return ConversationHandler.END
        
    await update.message.reply_text("Assalomu alaykum! Van Sales tizimiga xush kelibsiz.\nIltimos, Apteka yoki korxonangiz nomini kiriting:")
    return ASK_NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['partner_name'] = update.message.text
    
    # Request Phone number via Reply Keyboard for convenience
    contact_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Raqamni yuborish", request_contact=True)]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )
    
    await update.message.reply_text(
        "Rahmat! Endi telefon raqamingizni yuboring (yoki pastdagi tugmani bosing):",
        reply_markup=contact_keyboard
    )
    return ASK_PHONE

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Process either text input or contact card
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text
        
    chat_id = str(update.effective_chat.id)
    name = context.user_data.get('partner_name', 'Noma\'lum')
    
    models, uid = get_odoo_models()
    if not models:
        await update.message.reply_text("Tizim xatoligi.")
        return ConversationHandler.END

    # 1. Search existing partner by phone to link instead of duplicate
    if phone.startswith('+'):
        search_phone = phone
    else:
        search_phone = '+' + phone.lstrip('0')
        
    # Simple search (can be enhanced for format variations)
    existing_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search', [[('phone', 'ilike', phone[-9:])]])
    
    if existing_ids:
        # Link to existing
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'write', [existing_ids[0], {
            'telegram_chat_id': chat_id
        }])
    else:
        # Create new
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
            'name': name,
            'phone': phone,
            'telegram_chat_id': chat_id,
            'x_is_van_customer': True
        }])

    # Remove the bulky reply keyboard
    from telegram import ReplyKeyboardRemove
    await update.message.reply_text(
        "✅ Ro'yxatdan o'tdingiz!\nEndi botdan foydalanishingiz mumkin.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await update.message.reply_text(
        "Asosiy Menu:",
        reply_markup=build_main_menu()
    )
    return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Ro'yxatdan o'tish bekor qilindi. /start ni bosib qaytadan boshlashingiz mumkin.")
    return ConversationHandler.END


# --- MENU CALLBACKS ---

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Acknowledge the button press
    
    chat_id = str(update.effective_chat.id)
    data = query.data
    
    models, uid = get_odoo_models()
    if not models:
        await query.edit_message_text("Ma'lumotlarni olishda xatolik yuz berdi.")
        return

    # Find the partner
    partner_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search', [[('telegram_chat_id', '=', chat_id)]])
    if not partner_ids:
        await query.edit_message_text("Sizning hisobingiz topilmadi. Iltimos /start ni bosing.")
        return
        
    partner_id = partner_ids[0]

    if data == 'menu_balans':
        # Refresh the compute field before reading
        models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'get_partner_van_debt', [partner_id])
        partner_data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'read', [[partner_id], ['x_van_total_due']])
        if partner_data:
            debt = partner_data[0].get('x_van_total_due', 0.0)
            await query.edit_message_text(
                f"💰 <b>Sizning joriy qarzingiz (Balans):</b>\n\n💵 {debt:,.0f} so'm",
                parse_mode='HTML',
                reply_markup=build_main_menu()
            )
            
    elif data == 'menu_tranzaksiyalar':
        # Fetch van.dashboard.detail for this partner
        records = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'van.dashboard.detail', 'search_read', [
            [('partner_id', '=', partner_id)]
        ], {'fields': ['date', 'transaction_type', 'amount'], 'order': 'date desc', 'limit': 15})
        
        if not records:
             await query.edit_message_text("Tranzaksiyalar tarixi bo'sh.", reply_markup=build_main_menu())
             return
             
        msg = "📋 <b>So'nggi 15 ta tranzaksiya:</b>\n\n"
        for r in records:
            dt = r['date'] # "2026-03-01 14:30:00"
            ttype = r['transaction_type']
            icon = "✅ Kirim" if ttype == "kirim" else ("🛍 Savdo" if ttype == "sale" else "➖ Chiqim")
            msg += f"📅 {dt[:16]}\n  {icon} | {r['amount']:,.0f} so'm\n\n"
            
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=build_main_menu())

    elif data == 'menu_savdo_cheklari':
        # Fetch last 5 van.pos.order list
        orders = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'van.pos.order', 'search_read', [
            [('partner_id', '=', partner_id), ('state', '=', 'done')]
        ], {'fields': ['name', 'date', 'amount_total', 'line_ids'], 'order': 'date desc', 'limit': 5})
        
        if not orders:
             await query.edit_message_text("Savdo cheklari tarixi bo'sh.", reply_markup=build_main_menu())
             return
             
        msg = "🧾 <b>So'nggi 5 ta savdo cheki (Batafsil):</b>\n\n"
        for o in orders:
            dt = o['date'][:16]
            msg += f"📄 <b>{o['name']}</b> | 📅 {dt}\n"
            
            # Fetch lines for this order
            lines = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'van.pos.order.line', 'read', [
                o['line_ids'], ['product_id', 'qty', 'price_unit', 'subtotal']
            ])
            
            for l in lines:
                p_name = l['product_id'][1]
                msg += f" ▪️ {p_name}\n    {int(l['qty'])} x {l['price_unit']:,.0f} = {l['subtotal']:,.0f} so'm\n"
            
            msg += f"💰 <b>Jami: {o['amount_total']:,.0f} so'm</b>\n"
            msg += "---------------------------------\n\n"
            
        base_url = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'ir.config_parameter', 'get_param', ['van_telegram_odoo_url', ''])
        web_app_url = f"{base_url}/van/client/request?chat_id={chat_id}"
        
        button = {"text": "🛒 Zakaz berish"}
        if web_app_url.startswith('https://'):
            button["web_app"] = {"url": web_app_url}
        else:
            button["url"] = web_app_url
            
        reply_markup = {
            "inline_keyboard": [[button]]
        }
            
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)


async def generic_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler for text if they type something randomly"""
    await update.message.reply_text("Menyulardan foydalanish uchun /start yoki /menu buyrug'ini tering.")

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback command to reshow the main menu without registering"""
    await update.message.reply_text("Asosiy Menu:", reply_markup=build_main_menu())

def main():
    token = get_bot_token()
    if not token:
        logger.error("No Telegram Bot Token found in Odoo 'van.telegram.bot.token' sys parameter.")
        logger.error("Please add the token in the Odoo Interface before running this script.")
        # If testing without an interface, you can override token literally here
        # token = "YOUR_BOT_TOKEN_HERE"
        sys.exit(1)

    logger.info("Initializing Telegram Bot...")
    application = Application.builder().token(token).build()

    # Registration Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_cmd)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT | filters.CONTACT, handle_phone)]
        },
        fallbacks=[CommandHandler('cancel', cancel_registration)]
    )
    application.add_handler(conv_handler)

    # Hard Menu command
    application.add_handler(CommandHandler('menu', menu_cmd))

    # Inline Button callbacks
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Generic text fallback string
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generic_text_handler))

    # Run the bot forever!
    logger.info("Bot is polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
