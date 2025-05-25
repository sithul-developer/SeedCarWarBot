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

# Constants
ADMIN_IDS = [5742761331]  # Replace with your Telegram ID
PHONE_REGEX = re.compile(r'^\+?[0-9\s\-]{8,15}$')
PLATE_REGEX = re.compile(r'^[A-Z0-9-]{3,10}$')

# Conversation states
WAITING_PHONE, WAITING_PLATE, WAITING_CUSTOMER = range(3)

# Database
customer_registry = {}  # Format: {phone_number: {"admin_chat": int, "customer_chat": int, "status": str, "plate": str}}


# Helper functions
def clean_phone_number(phone: str) -> str:
    """Normalize phone number to Cambodian format (855XXXXXXXXX)"""
    clean_phone = ''.join(c for c in phone if c.isdigit())
    return '855' + clean_phone if not clean_phone.startswith('855') else clean_phone


# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id in ADMIN_IDS:
        await update.message.reply_text(
            "👨‍🔧 *Admin Panel - Speed Car Wash*\n\n"
            "Available commands - ពាក្យបញ្ជាដែលអាចប្រើបាន:\n\n"
            "/register - ចុះឈ្មោះអតិថិជនថ្មី\n"
            "                 Register a new customer\n\n"
            "/ready - ជូនដំណឹងទៅអតិថិជនថារថយន្តរួចរាល់\n" 
            "               Notify customer their car is ready\n\n"
            "/status - ពិនិត្យមើលការចុះឈ្មោះបច្ចុប្បន្ន\n"
            "                Check current registrations\n\n"
            "/cancel - បោះបង់ប្រតិបត្តិការបច្ចុប្បន្ន\n"
            "               Cancel the current operation",
            parse_mode='Markdown'
        )
    else:
        if context.args and context.args[0] in customer_registry:
            phone = context.args[0]
            customer_chat = update.effective_chat.id
            
            customer_registry[phone]["customer_chat"] = customer_chat
            customer_registry[phone]["status"] = "waiting"
            
            await context.bot.send_message(
                chat_id=customer_registry[phone]["admin_chat"],
                text=(
                    f"📲 *អតិថិជនបានចុះឈ្មោះតាម QR*\n"
                    f"📱 លេខទូរស័ព្ទ៖ {phone}\n"
                    f"🚗 លេខផ្លាក៖ {customer_registry[phone].get('plate', 'មិនមាន')}\n"
                    f"ស្ថានភាព៖ កំពុងរង់ចាំសេវា\n\n"
                    f"📲 *Customer Registered via QR*\n"
                    f"📱 Phone: {phone}\n"
                    f"🚗 Plate: {customer_registry[phone].get('plate', 'Not provided')}\n"
                    f"Status: Waiting for service"
                ),
                parse_mode='Markdown'
            )
            
            await update.message.reply_text(
                f"🚗 *ការចុះឈ្មោះបានជោគជ័យ!*\n\n"
                f"📱 លេខទូរស័ព្ទ៖ {phone}\n"
                f"🚗 លេខផ្លាក៖ {customer_registry[phone].get('plate', 'មិនមាន')}\n\n"
                "អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់។\n\n"
                f"🚗 *Registration Complete!*\n\n"
                f"📱 Phone: {phone}\n"
                f"🚗 Plate: {customer_registry[phone].get('plate', 'Not provided')}\n\n"
                "You'll be notified when your car is ready.",
                parse_mode='Markdown'
            )
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "🚗 *សូមស្វាគមន៍មកកាន់ Speed Car Wash!*\n\n"
                "សូមផ្ញើលេខទូរស័ព្ទរបស់អ្នកដើម្បីចុះឈ្មោះទទួលការជូនដំណឹង។\n"
                "ឧទាហរណ៍៖ +855 xxx xxx xxxx\n\n"
                "🚗 *Welcome to Speed Car Wash!*\n\n"
                "Please send your phone number to register for notifications.\n"
                "Example: +855 xxx xxx xxxx",
                parse_mode='Markdown'
            )
            return WAITING_CUSTOMER


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "❌ អ្នកមិនមានសិទ្ធិប្រើបញ្ជានេះទេ។\n"
            "❌ You are not authorized to use this command."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "១. សូមផ្ញើលេខទូរស័ព្ទរបស់អតិថិជន\n"
        "២. ឧទាហរណ៍៖ 📱+855 xxx xxx xxxx\n"
        "៣. ចូរបញ្ជាក់ថាបានបញ្ចូលលេខកូដប្រទេស\n"
        "៤. វាយ /cancel ដើម្បីបោះបង់ ប្រតិបត្តិការ\n\n"
        "1. Please send the customer's phone number\n"
        "2. Example: 📱+855 xxx xxx xxxx\n"
        "3. Make sure to include the country code.\n"
        "4. Type /cancel to abort."
    )
    return WAITING_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    
    if not PHONE_REGEX.match(phone):
        await update.message.reply_text(
            "❌ ទម្រង់លេខទូរស័ព្ទមិនត្រឹមត្រូវ។\n"
            "សូមបញ្ចូលលេខទូរស័ព្ទដែលត្រឹមត្រូវ (ឧទាហរណ៍៖ +855 XXX XXX XXX)។\n\n"
            "❌ Invalid phone number format.\n"
            "Please enter a valid phone number (e.g., +855 XXX XXX XXX)."
        )
        return WAITING_PHONE
    
    clean_phone = clean_phone_number(phone)
    
    if clean_phone in customer_registry:
        await update.message.reply_text(
            f"ℹ️ លេខទូរស័ព្ទ {clean_phone} នេះបានចុះឈ្មោះក្នុងប្រព័ន្ធរួចហើយ។\n"
            f"ℹ️ Phone number {clean_phone} is already registered."
        )
        return ConversationHandler.END
    
    context.user_data['register_phone'] = clean_phone
    await update.message.reply_text(
        "សូមផ្ញើលេខផ្លាករថយន្តឥឡូវនេះ:\n"
        "Now please send the vehicle plate number:"
    )
    return WAITING_PLATE


async def receive_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plate = update.message.text.strip().upper()
    if not PLATE_REGEX.match(plate):
        await update.message.reply_text(
            "❌ *ទម្រង់លេខផ្លាកមិនត្រឹមត្រូវ!*\n\n"
            "សូមបញ្ចូលលេខផ្លាកដែលត្រឹមត្រូវ។\n"
            "ឧទាហរណ៍៖ `ABC1234`, `XYZ-9876`, ឬ `KHM2023`\n\n"
            "❌ *Invalid plate format!*\n\n"
            "Please enter a valid plate number.\n"
            "Example: `ABC1234`, `XYZ-9876`, or `KHM2023`",
            parse_mode='Markdown'
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

    # Generate QR code
    bot_username = (await context.bot.get_me()).username
    deep_link = f"https://t.me/{bot_username}?start={clean_phone}"

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(deep_link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    bio.name = 'qr_code.png'
    img.save(bio, 'PNG')
    bio.seek(0)

    caption = (
        f"✅ *អតិថិជនត្រូវបានចុះឈ្មោះ* ✅\n\n"
        f"📱 លេខទូរស័ព្ទ: {clean_phone}\n"
        f"🚗 លេខផ្លាក: {plate}\n\n"
        "1. បង្ហាញកូដ QR នេះទៅអតិថិជន\n"
        "2. អតិថិជនស្កែនវាតាមម៉ាស៊ីនថតទូរស័ព្ទ\n"
        "3. ពួកគេនឹងត្រូវបានចុះឈ្មោះដោយស្វ័យប្រវត្តិ\n\n"
        "ឬផ្ញើតំណផ្ទាល់នេះទៅពួកគេ:\n"
        f"{deep_link}\n\n"
        "✅ *Customer Registered*\n\n"
        f"📱 Phone: {clean_phone}\n"
        f"🚗 Plate: {plate}\n\n"
        "1. Show this QR code to the customer\n"
        "2. They scan it with their phone camera\n"
        "3. They'll be automatically registered\n\n"
        "Or send them this direct link:\n"
        f"{deep_link}"
    )

    await update.message.reply_photo(
        photo=bio,
        caption=caption,
        parse_mode='Markdown'
    )

    return ConversationHandler.END


async def receive_customer_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    clean_phone = clean_phone_number(phone)
    customer_chat = update.effective_chat.id
    
    if clean_phone not in customer_registry:
        await update.message.reply_text(
            "❌ *រកមិនឃើញលេខទូរស័ព្ទ*\n\n"
            "លេខនេះមិនទាន់បានចុះឈ្មោះនៅឡើយ។ សូមសុំព័ត៌មាននៅគេហទំព័រសេវាកម្ម។\n\n"
            "❌ *Phone number not found*\n\n"
            "This number isn't registered yet. Please ask at the service desk.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    customer_registry[clean_phone]["customer_chat"] = customer_chat
    customer_registry[clean_phone]["status"] = "waiting"
    
    admin_message = (
        f"📲 *អតិថិជនបានចុះឈ្មោះ*\n\n"
        f"📱 លេខទូរស័ព្ទ: {clean_phone}\n"
        f"🚗 លេខផ្លាក: {customer_registry[clean_phone].get('plate', 'មិនមាន')}\n"
        f"ស្ថានភាព: កំពុងរង់ចាំសេវា\n\n"
        f"📲 *Customer Registered*\n\n"
        f"📱 Phone: {clean_phone}\n"
        f"🚗 Plate: {customer_registry[clean_phone].get('plate', 'Not provided')}\n"
        f"Status: Waiting for service"
    )
    
    customer_message = (
        f"📱 *សូមអរគុណ!*\n\n"
        f"📱 លេខទូរស័ព្ទ: {clean_phone}\n"
        f"🚗 លេខផ្លាក: {customer_registry[clean_phone].get('plate', 'មិនមាន')}\n\n"
        "អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់។\n\n"
        f"📱 *Thank you!*\n\n"
        f"📱 Phone: {clean_phone}\n"
        f"🚗 Plate: {customer_registry[clean_phone].get('plate', 'Not provided')}\n\n"
        "You'll be notified when your car is ready."
    )
    
    await context.bot.send_message(
        chat_id=customer_registry[clean_phone]["admin_chat"],
        text=admin_message,
        parse_mode='Markdown'
    )
    
    await update.message.reply_text(
        customer_message,
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "❌ អ្នកមិនមានសិទ្ធិប្រើបញ្ជានេះទេ។\n"
            "❌ You are not authorized to use this command."
        )
        return
    
    ready_customers = {
        phone: data for phone, data in customer_registry.items()
        if data["customer_chat"] and data["status"] == "waiting"
    }
    
    if not ready_customers:
        await update.message.reply_text(
            "🚫 គ្មានអតិថិជនណាកំពុងរង់ចាំការជូនដំណឹងទេ។\n"
            "🚫 No customers currently waiting for notification."
        )
        return
    
    buttons = [
        [InlineKeyboardButton(f"{phone} ({data.get('plate', 'No plate')})", callback_data=f"ready_{phone}")]
        for phone, data in ready_customers.items()
    ]
    
    await update.message.reply_text(
        "📢 ជ្រើសរើសអតិថិជនដើម្បីជូនដំណឹង (លេខទូរស័ព្ទ - លេខផ្លាក):\n"
        "📢 Select customer to notify (Phone - Plate):", 
        reply_markup=InlineKeyboardMarkup(buttons)
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
                text=(
                    "✨ *រថយន្តរបស់អ្នករួចរាល់ហើយ!* ✨\n\n"
                    f"📱 លេខទូរស័ព្ទ: {phone}\n"
                    f"🚗 លេខផ្លាក: {plate}\n"
                    "📍 ទីតាំង: លាងរថយន្ត Speed Car Wash BVM PAC\n\n"
                    "សូមមកយករថយន្តរបស់អ្នក។\n\n"
                    "✨ *Your car is ready!* ✨\n\n"
                    f"📱 Phone: {phone}\n"
                    f"🚗 Plate: {plate}\n"
                    "📍 Location: Speed Car Wash BVM PAC\n\n"
                    "Please come pick up your vehicle."
                ),
                parse_mode='Markdown'
            )
            
            await query.edit_message_text(
                f"អតិថិជនត្រូវបានជូនដំណឹងសម្រាប់:\n📱 {phone}\n🚗 {plate}\n\n"
                f"✅ Customer notified for:\n📱 {phone}\n🚗 {plate}"
            )
            customer_registry[phone]["status"] = "ready"
        else:
            await query.edit_message_text(
                "❌ រកមិនឃើញអតិថិជនទេ\n"
                "❌ Could not find customer."
            )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "❌ អ្នកមិនមានសិទ្ធិប្រើបញ្ជានេះទេ។\n"
            "❌ You are not authorized to use this command."
        )
        return
    
    if not customer_registry:
        await update.message.reply_text(
            "ℹ️ គ្មានអតិថិជនណាត្រូវបានចុះឈ្មោះនៅពេលបច្ចុប្បន្នទេ។\n"
            "ℹ️ No customers currently registered."
        )
        return
    
    status_message = "📊 *បច្ចុប្បន្នការចុះឈ្មោះរួច\nCurrent Registrations*\n\n"
    for phone, data in customer_registry.items():
        status_message += (
            f"📱 *លេខទូរស័ព្ទ:* {phone}\n"
            f"🚗 *លេខផ្លាក:* {data.get('plate', 'មិនមាន')}\n"
            f"• *ស្ថានភាព:* {data.get('status', 'មិនស្គាល់')}\n"
            f"• *អតិថិជន:* {'បានចុះឈ្មោះ' if data['customer_chat'] else 'កំពុងរង់ចាំ'}\n\n"
            f"📱 *Phone:* {phone}\n"
            f"🚗 *Plate:* {data.get('plate', 'Not provided')}\n"
            f"• *Status:* {data.get('status', 'unknown')}\n"
            f"• *Customer:* {'registered' if data['customer_chat'] else 'pending'}\n\n"
        )
    
    await update.message.reply_text(status_message, parse_mode='Markdown')


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ប្រតិបត្តិការត្រូវបានបោះបង់។\n"
        "Operation cancelled."
    )
    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token("8034394783:AAETP8ska_DaX53cqVXuotPEVMzfkeUeKjA").build()

    # Conversation handlers
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

    # Register handlers
    app.add_handler(reg_conv_handler)
    app.add_handler(customer_conv_handler)
    app.add_handler(CommandHandler('ready', ready))
    app.add_handler(CommandHandler('status', status))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🚗 Speed Car Wash bot is running...")
    app.run_polling()


if __name__ == '__main__':
    main()