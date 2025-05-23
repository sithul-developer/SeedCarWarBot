from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import qrcode
from io import BytesIO
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler
)
import re

# Database setup
customer_registry = {}  # Format: {phone_number: {"admin_chat": int, "customer_chat": int, "status": str, "plate": str}}

# Admin configuration
ADMIN_IDS = [5742761331]  # Replace with your Telegram ID

# Conversation states
WAITING_PHONE, WAITING_PLATE, WAITING_CUSTOMER = range(3)

# Phone number validation regex
PHONE_REGEX = re.compile(r'^\+?[0-9\s\-]{8,15}$')
# Plate validation regex (adjust according to your country's format)
PLATE_REGEX = re.compile(r'^[A-Z0-9]{2,10}$')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id in ADMIN_IDS:
        await update.message.reply_text(
            "👨‍🔧 *Admin Panel - Speed Car Wash*\n\n"
            "Available commands:\n"
            "/register - Register a new customer\n"
            "/ready - Notify customer their car is ready\n"
            "/status - Check current registrations",
            parse_mode='Markdown'
        )
    else:
        if context.args and context.args[0] in customer_registry:
            phone = context.args[0]
            customer_chat = update.effective_chat.id
            
            customer_registry[phone]["customer_chat"] = customer_chat
            customer_registry[phone]["status"] = "waiting"
            
            admin_chat = customer_registry[phone]["admin_chat"]
            await context.bot.send_message(
                chat_id=admin_chat,
                text=f"📲 *Customer Registered via QR*\n\n"
                     f"📱 Phone: {phone}\n"
                     f"🚗 Plate: {customer_registry[phone].get('plate', 'Not provided')}\n"
                     f"Status: Waiting for service",
                parse_mode='Markdown'
            )
            
            await update.message.reply_text(
                f"🚗 *Registration Complete!*\n\n"
                f"📱 Phone: {phone}\n"
                f"🚗 Plate: {customer_registry[phone].get('plate', 'Not provided')}\n\n"
                "You'll be notified when your car is ready.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "🚗 *Welcome to Speed Car Wash!*\n\n"
                "Please send your phone number to register for notifications.\n"
                "Example: +855 xxx xxx xxxx",
                parse_mode='Markdown'
            )
            return WAITING_CUSTOMER

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Please send the customer's phone number (e.g., +855 xxx xxx xxxx):\n\n"
        "Type /cancel to abort."
    )
    return WAITING_PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    
    if not PHONE_REGEX.match(phone):
        await update.message.reply_text(
            "❌ Invalid phone number format.\n"
            "Please enter a valid phone number (e.g., +855 XXX XXX XXX)."
        )
        return WAITING_PHONE
    
    clean_phone = ''.join(c for c in phone if c.isdigit())
    if not clean_phone.startswith('855'):
        clean_phone = '855' + clean_phone[-8:]  # Cambodian format
    
    if clean_phone in customer_registry:
        await update.message.reply_text(f"ℹ️ Phone number {clean_phone} is already registered.")
        return ConversationHandler.END
    
    context.user_data['register_phone'] = clean_phone
    await update.message.reply_text(
        "Now please send the vehicle plate number:"
    )
    return WAITING_PLATE

async def receive_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plate = update.message.text.strip().upper()
    
    if not PLATE_REGEX.match(plate):
        await update.message.reply_text(
            "❌ Invalid plate format.\n"
            "Please enter a valid plate number (e.g., ABC1234)."
        )
        return WAITING_PLATE
    
    clean_phone = context.user_data['register_phone']
    admin_chat = update.effective_chat.id
    
    customer_registry[clean_phone] = {
        "admin_chat": admin_chat,
        "customer_chat": None,
        "status": "registered",
        "plate": plate
    }
    
    bot_username = (await context.bot.get_me()).username
    deep_link = f"https://t.me/{bot_username}?start={clean_phone}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    bio.name = 'qr_code.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    
    await update.message.reply_photo(
        photo=bio,
        caption=f"✅ *Customer Registered*\n\n"
               f"📱 Phone: {clean_phone}\n"
               f"🚗 Plate: {plate}\n\n"
               "1. Show this QR code to the customer\n"
               "2. They scan it with their phone camera\n"
               "3. They'll be automatically registered\n\n"
               "Or send them this direct link:\n"
               f"`{deep_link}`",
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

async def receive_customer_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    clean_phone = ''.join(c for c in phone if c.isdigit())
    if not clean_phone.startswith('855'):
        clean_phone = '855' + clean_phone[-8:]  # Cambodian format
    
    customer_chat = update.effective_chat.id
    
    if clean_phone not in customer_registry:
        await update.message.reply_text(
            "❌ *Phone number not found*\n\n"
            "This number isn't registered yet. Please ask at the service desk.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    customer_registry[clean_phone]["customer_chat"] = customer_chat
    customer_registry[clean_phone]["status"] = "waiting"
    
    admin_chat = customer_registry[clean_phone]["admin_chat"]
    await context.bot.send_message(
        chat_id=admin_chat,
        text=f"📲 *Customer Registered*\n\n"
             f"📱 Phone: {clean_phone}\n"
             f"🚗 Plate: {customer_registry[clean_phone].get('plate', 'Not provided')}\n"
             f"Status: Waiting for service",
        parse_mode='Markdown'
    )
    
    await update.message.reply_text(
        f"📱 *Thank you!*\n\n"
        f"📱 Phone: {clean_phone}\n"
        f"🚗 Plate: {customer_registry[clean_phone].get('plate', 'Not provided')}\n\n"
        "You'll be notified when your car is ready.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

async def ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    
    ready_customers = {
        phone: data for phone, data in customer_registry.items()
        if data["customer_chat"] and data["status"] == "waiting"
    }
    
    if not ready_customers:
        await update.message.reply_text("🚫 No customers currently waiting for notification.")
        return
    
    buttons = []
    for phone, data in ready_customers.items():
        plate = data.get('plate', 'No plate')
        buttons.append([InlineKeyboardButton(
            f"{phone} ({plate})", 
            callback_data=f"ready_{phone}"
        )])
    
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "Select customer to notify (Phone - Plate):", 
        reply_markup=markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("ready_"):
        phone = query.data[6:]
        customer_data = customer_registry.get(phone)
        
        if customer_data and customer_data["customer_chat"]:
            plate = customer_data.get('plate', 'unknown plate')
            await context.bot.send_message(
                chat_id=customer_data["customer_chat"],
                text="✨ *Your car is ready!* ✨\n\n"
                     f"📱 Phone: {phone}\n"
                     f"🚗 Plate: {plate}\n"
                     "📍 Location: Speed Car Wash BVM PAC\n\n"
                     "Please come pick up your vehicle.",
                parse_mode='Markdown'
            )
            
            await query.edit_message_text(f"✅ Customer notified for:\n📱 {phone}\n🚗 {plate}")
            customer_registry[phone]["status"] = "ready"
        else:
            await query.edit_message_text("❌ Could not find customer.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    
    if not customer_registry:
        await update.message.reply_text("ℹ️ No customers currently registered.")
        return
    
    status_message = "📊 *Current Registrations*\n\n"
    for phone, data in customer_registry.items():
        status_message += (
            f"📱 *Phone:* {phone}\n"
            f"🚗 *Plate:* {data.get('plate', 'Not provided')}\n"
            f"• *Status:* {data.get('status', 'unknown')}\n"
            f"• *Customer:* {'registered' if data['customer_chat'] else 'pending'}\n\n"
        )
    
    await update.message.reply_text(status_message, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token("7852833201:AAF0uLiUoIIRm6gBYK2fuPTM7t56QgN5leU").build()

    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            WAITING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            WAITING_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plate)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    customer_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAITING_CUSTOMER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_customer_phone)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(reg_conv_handler)
    app.add_handler(customer_conv_handler)
    app.add_handler(CommandHandler('ready', ready))
    app.add_handler(CommandHandler('status', status))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🚗 Speed Car Wash bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()