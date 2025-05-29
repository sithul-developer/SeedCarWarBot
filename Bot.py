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
import json
import os
from datetime import datetime

# Constants
ADMIN_FILE = "admins.json"  # File to store admin IDs
GROUP_FILE = "group_id.json"
DEFAULT_ADMINS = [5742761331,509847275]  # Your initial admin ID 509847275
GROUP_ID = -4813155053
PLATE_REGEX = re.compile(r'^[A-Z0-9-]{3,10}$')

# Conversation states
WAITING_PLATE, WAITING_CUSTOMER = range(2)

# Database
customer_registry = {}  # Format: {queue_number: {"admin_chat": int, "customer_chat": int, "status": str, "plate": str, "timestamp": str}}
queue_counter = 1  # Initialize queue counter

# Helper functions
def load_admins():
    """Load admin IDs from file or create with default if not exists"""
    if os.path.exists(ADMIN_FILE):
        try:
            with open(ADMIN_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    raise ValueError("Admin file is empty")
                data = json.loads(content)
            if isinstance(data, list):
                return data
            else:
                raise ValueError("Admin file is not a list")
        except (json.JSONDecodeError, ValueError, IOError, TypeError):
            try:
                os.remove(ADMIN_FILE)
            except Exception:
                pass
    try:
        with open(ADMIN_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_ADMINS, f)
    except Exception as e:
        print(f"Error writing admin file: {e}")
    return DEFAULT_ADMINS

def save_admins(admin_list):
    """Save admin IDs to file"""
    with open(ADMIN_FILE, 'w') as f:
        json.dump(admin_list, f)

def load_group_id():
    """Load group ID from file or return None if not set"""
    try:
        if os.path.exists(GROUP_FILE):
            with open(GROUP_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return None
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    return None
                if isinstance(data, int):
                    return data
                elif isinstance(data, str):
                    try:
                        return int(data)
                    except ValueError:
                        return None
                elif isinstance(data, dict) and "group_id" in data:
                    try:
                        return int(data["group_id"])
                    except (ValueError, TypeError):
                        return None
                else:
                    return None
    except (json.JSONDecodeError, IOError):
        pass
    return None

def save_group_id(group_id):
    """Save group ID to file"""
    with open(GROUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(group_id, f)

def generate_queue_number():
    """Generate a unique queue number with date prefix"""
    global queue_counter
    today = datetime.now().strftime("%Y%m%d")
    queue_number = f"{today}-{queue_counter:03d}"
    queue_counter += 1
    return queue_number

# Initialize admins and group_id
admins = load_admins()
group_id = load_group_id() or GROUP_ID

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id in admins:
        await update.message.reply_text(
            "👨‍🔧*Admin Panel - Speed Car Wash*\n\n"
            "ពាក្យបញ្ជាដែលអាចប្រើបាន:\n"
            "/register - ចុះឈ្មោះអតិថិជនថ្មី\n"
            "/ready - ជូនដំណឹងទៅអតិថិជនថារថយន្តរួចរាល់\n" 
            "/cancel - បោះបង់ប្រតិបត្តិការបច្ចុប្បន្ន\n\n"
            "Available commands :\n"
            "/register - Register a new customer\n"
            "/ready - Notify customer their car is ready\n"
            "/cancel - Cancel the current operation",
            parse_mode='Markdown'
        )
    else:
        # Try to extract argument from /start <queue_number> deep link
        queue_number = None
        if update.message and update.message.text:
            parts = update.message.text.strip().split()
            if len(parts) > 1:
                queue_number = parts[1]
        
        if queue_number and queue_number in customer_registry:
            customer_chat = update.effective_chat.id
            customer_registry[queue_number]["customer_chat"] = customer_chat
            customer_registry[queue_number]["status"] = "waiting"

            await context.bot.send_message(
                chat_id=customer_registry[queue_number]["admin_chat"],
                text=(
                    f"*អតិថិជនបានចុះឈ្មោះតាមរយៈ QR Code ដោយជោគជ័យ*\n\n"
                    f"🛂 លេខគណនី : {queue_number}\n"
                    f"🚗 ផ្លាកលេខ : {customer_registry[queue_number].get('plate', 'មិនមាន')}\n"
                    f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n"
                    f"⏳ ស្ថានភាព៖ កំពុងរង់ចាំសេវា\n\n"
                    f"*Customer has successfully registered through QR Code*\n\n"
                    f"🛂 Queue Number : {queue_number}\n"
                    f"🚗 Plate : {customer_registry[queue_number].get('plate', 'Not provided')}\n"
                    f"👤 Customer Name : {update.effective_user.full_name}\n\n"
                    f"⏳ Status : Waiting for service"
                ),
                parse_mode='Markdown'
            )

            await update.message.reply_text(
                f"ការចុះឈ្មោះអតិថិជនបានដោយជោគជ័យ!\n\n"
                f"🛂 លេខគណនី : {queue_number}\n"
                f"🚗 ផ្លាកលេខ : {customer_registry[queue_number].get('plate', 'មិនមាន')}\n"
                f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n\n"
                "អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់។\n\n"
                f"Successful customer registration completed!\n\n"
                f"🛂 Queue Number : {queue_number}\n"
                f"🚗 Plate : {customer_registry[queue_number].get('plate', 'Not provided')}\n"
                f"👤 Customer Name : {update.effective_user.full_name}\n\n"
                "You'll be notified when your car is ready.",
                parse_mode='Markdown'
            )
            return ConversationHandler.END
        else:
            queue_number = generate_queue_number()
            customer_chat = update.effective_chat.id
            
            # Store minimal info until plate is provided
            customer_registry[queue_number] = {
                "admin_chat": None,  # Will be set when admin completes registration
                "customer_chat": customer_chat,
                "status": "pending",
                "plate": None,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            context.user_data['queue_number'] = queue_number
            
            await update.message.reply_text(
                "🚗 *សូមស្វាគមន៍មកកាន់ Speed Car Wash!*\n\n"
                "សូមផ្ញើផ្លាកលេខរថយន្តរបស់អ្នក។\n"
                "ឧទាហរណ៍៖ ABC-1234\n\n"
                "🚗 *Welcome to Speed Car Wash!*\n\n"
                "Please send your vehicle plate number.\n"
                "Example: ABC-1234",
                parse_mode='Markdown'
            )
            return WAITING_PLATE

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        await update.message.reply_text(
            "❌ អ្នកមិនមានសិទ្ធិប្រើបញ្ជានេះទេ។\n"
            "❌ You are not authorized to use this command."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "✅ សូមផ្ញើផ្លាកលេខរថយន្តរបស់អតិថិជន\n"
        "✅ Please send the vehicle plate number\n\n"
        "Type /cancel to abort."
    )
    return WAITING_PLATE

async def receive_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plate = update.message.text.strip().upper()
    if not PLATE_REGEX.match(plate):
        await update.message.reply_text(
            "❌ ទម្រង់ផ្លាកលេខមិនត្រឹមត្រូវ។ សូមព្យាយាមម្តងទៀត។\n"
            "❌ Invalid plate format. Please try again.\n\n"
            "Type /cancel to abort.",
            parse_mode='Markdown'
        )
        return WAITING_PLATE
    # Check if plate exists in registry
    for existing_data in customer_registry.values():
        if existing_data.get('plate') == plate:
            await update.message.reply_text(
                "⚠️ ផ្លាកលេខនេះបានចុះឈ្មោះរួចហើយ។ សូមបញ្ចូលលេខផ្សេង។\n"
                "⚠️ This plate number is already registered. Please send a different one.\n\n"
                "Type /cancel to abort."
            )
            return WAITING_PLATE
    if update.effective_user.id in admins:  # Admin registration flow
        queue_number = generate_queue_number()
        admin_chat = update.effective_chat.id
        
        customer_registry[queue_number] = {
            "admin_chat": admin_chat,
            "customer_chat": None,
            "status": "registered",
            "plate": plate,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Generate QR code
        bot_username = (await context.bot.get_me()).username
        deep_link = f"https://t.me/{bot_username}?start={queue_number}"

        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(deep_link)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        bio.name = 'qr_code.png'
        img.save(bio, 'PNG')
        bio.seek(0)

        caption = (
            "បានចុះឈ្មោះអតិថិជនថ្មីរួចរាល់ \n\n"
            f"🛂 លេខគណនី : {queue_number}\n"
            f"🚗 ផ្លាកលេខ : {plate}\n\n"
            "1. បង្ហាញកូដ QR នេះទៅអតិថិជន\n"
            "2. អតិថិជនស្កែនវាតាមម៉ាស៊ីនថតទូរស័ព្ទ\n"
            "3. ពួកគេនឹងត្រូវបានចុះឈ្មោះដោយស្វ័យប្រវត្តិ\n"
            "ឬផ្ញើតំណផ្ទាល់នេះទៅពួកគេ:\n"
            f"{deep_link}\n\n"
            "New customer registration completed\n\n"
            f"🛂 Queue Number : {queue_number}\n"
            f"🚗 Plate : {plate}\n\n"
            "1. Show this QR code to the customer\n"
            "2. They scan it with their phone camera\n"
            "3. They'll be automatically registered\n"
            "Or send them this direct link:\n"
            f"{deep_link}"
        )

        await update.message.reply_photo(
            photo=bio,
            caption=caption
        )
    else:  # Customer self-registration flow
        queue_number = context.user_data['queue_number']
        customer_registry[queue_number].update({
            "plate": plate,
            "status": "waiting"
        })
        
        # Notify customer
        await update.message.reply_text(
            f"ការចុះឈ្មោះអតិថិជនបានដោយជោគជ័យ!\n\n"
            f"🛂 លេខគណនី : {queue_number}\n"
            f"🚗 ផ្លាកលេខ : {plate}\n"
            f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n\n"
            "អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់។\n\n"
            f"Successful customer registration completed!\n\n"
            f"🛂 Queue Number : {queue_number}\n"
            f"🚗 Plate : {plate}\n"
            f"👤 Customer Name : {update.effective_user.full_name}\n\n"
            "You'll be notified when your car is ready.",
            parse_mode='Markdown'
        )
        
        # Find an admin to notify (could be enhanced to notify all admins)
        if admins:
            admin_chat_id = admins[0]  # Notify the first admin
            customer_registry[queue_number]["admin_chat"] = admin_chat_id
            
            await context.bot.send_message(
                chat_id=admin_chat_id,
                text=(
                    f"*អតិថិជនបានចុះឈ្មោះដោយខ្លួនឯងដោយជោគជ័យ*\n\n"
                    f"🛂 លេខគណនី : {queue_number}\n"
                    f"🚗 ផ្លាកលេខ : {plate}\n"
                    f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n"
                    f"⏳ ស្ថានភាព៖ កំពុងរង់ចាំសេវា\n\n"
                    
                    f"*Customer has self-registered successfully*\n\n"
                    f"🛂 Queue Number : {queue_number}\n"
                    f"🚗 Plate : {plate}\n"
                    f"👤 Customer Name : {update.effective_user.full_name}\n"
                    f"⏳ Status : Waiting for service\n\n"
                    
                    
                ),
                parse_mode='Markdown'
            )
    
    return ConversationHandler.END

async def ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        await update.message.reply_text(
            "❌ អ្នកមិនមានសិទ្ធិប្រើបញ្ជានេះទេ។\n"
            "❌ You are not authorized to use this command."
        )
        return
    
    ready_customers = {
        qn: data for qn, data in customer_registry.items()
        if data["customer_chat"] and data["status"] == "waiting"
    }
    
    if not ready_customers:
        await update.message.reply_text(
            "🚫 គ្មានអតិថិជនណាកំពុងរង់ចាំការជូនដំណឹងទេ។\n"
            "🚫 No customers currently waiting for notification."
        )
        return
    
    buttons = [
        [InlineKeyboardButton(f"{qn} ({data.get('plate', 'No plate')})", callback_data=f"ready_{qn}")]
        for qn, data in ready_customers.items()
    ]
    
    await update.message.reply_text(
        "📢 ជ្រើសរើសអតិថិជនដើម្បីជូនដំណឹង (លេខគណនី - ផ្លាកលេខ):\n"
        "📢 Select customer to notify (Queue - Plate):", 
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("ready_"):
        queue_number = query.data[6:]
        customer_data = customer_registry.get(queue_number)
        
        if customer_data and customer_data["customer_chat"]:
            plate = customer_data.get('plate', 'unknown plate')
            await context.bot.send_message(
                chat_id=customer_data["customer_chat"],
                text=(
                f"✨ *ជំរាបសួរ! រថយន្តរបស់លោកអ្នកត្រូវបានលាងសំអាតរួចរាល់ហើយ។ !* ✨\n\n"
                f"🛂 លេខគណនី : {queue_number}\n"
                f"🚗 ផ្លាកលេខ : {plate}\n"
                f"👤 ឈ្មោះបុគ្គលិក : {update.effective_user.full_name}\n\n"
                "សូមអរគុណសម្រាប់ការរង់ចាំ និងការជឿទុកចិត្តលើសេវាកម្មរបស់យើងខ្ញុំ។ 🚗✨\n\n"
                "✨ *Dear valued customer! Your car has been washed and is now ready.* ✨\n\n"
                f"🛂 Queue Number : {queue_number}\n"
                f"🚗 Plate : {plate}\n"
                f"👤 Staff Name : {update.effective_user.full_name}\n\n"
                "Thank you for your patience and trust in our service."
                ),
                parse_mode='Markdown'
            )
            await context.bot.send_message(
                chat_id=customer_data["admin_chat"],
                text=(
                f"📢 បានជូនដំណឹងអតិថិជនដោយជោគជ័យ\n\n"
                f"🛂 លេខគណនី : {queue_number}\n"
                f"🚗 ផ្លាកលេខ : {plate}\n"
                f"👤 ឈ្មោះបុគ្គលិក : {update.effective_user.full_name}\n\n"
                f"📢 Successfully notified customer\n\n"
                f"🛂 Queue Number : {queue_number}\n"
                f"🚗 Plate : {plate}\n"
                f"👤 Staff Name : {update.effective_user.full_name}\n\n"
                ),
                parse_mode='Markdown'
            )
            customer_registry[queue_number]["status"] = "ready"
        else:
            await query.edit_message_text(
                "❌ រកមិនឃើញអតិថិជនទេ\n"
                "❌ Could not find customer."
            )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ប្រតិបត្តិការត្រូវបានបោះបង់។\n"
        "Operation cancelled."
    )
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admins:
        help_text = (
            "🛠 *Speed Car Wash Bot Help* 🛠\n\n"
            "*Admin Commands:*\n"
            "/register - Register a new customer\n"
            "/ready - Notify customer their car is ready\n"
            "/cancel - Cancel current operation\n\n"
            "*Customer Commands:*\n"
            "/start - Begin registration process\n\n"
            "*General Commands:*\n"
            "/help - Show this help message\n\n"
            "ជំនួយសម្រាប់ប្រព័ន្ធលាងរថយន្ត Speed Car Wash\n"
            "ពាក្យបញ្ជាសម្រាប់អ្នកគ្រប់គ្រង៖\n"
            "/register - ចុះឈ្មោះអតិថិជនថ្មី\n"
            "/ready - ជូនដំណឹងអតិថិជនថារថយន្តរួចរាល់\n"
            "/cancel - បោះបង់ប្រតិបត្តិការបច្ចុប្បន្ន\n\n"
            "ពាក្យបញ្ជាសម្រាប់អតិថិជន៖\n"
            "/start - ចាប់ផ្តើមដំណើរការចុះឈ្មោះ"
        )
    else:
        help_text = (
            "🚗 *Speed Car Wash Customer Help* 🚗\n\n"
            "To register for car wash notifications:\n"
            "1. Send /start command\n"
            "2. Provide your vehicle plate number when asked\n"
            "3. You'll be notified when your car is ready\n\n"
            "សូមអរគុណសម្រាប់ការប្រើប្រាស់សេវាកម្មរបស់យើង។\n"
            "ដើម្បីចុះឈ្មោះទទួលការជូនដំណឹង៖\n"
            "1. បញ្ជូនពាក្យបញ្ជា /start\n"
            "2. ផ្ញើផ្លាកលេខរថយន្តរបស់អ្នកនៅពេលស្នើសុំ\n"
            "3. អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់"
        )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

# Admin management commands (unchanged from your original code)
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add one or multiple admins at once"""
    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "• Add single admin: `/addadmin 123456789`\n"
            "• Add multiple admins: `/addadmin 123456789 987654321 555555555`"
        )
        return

    new_admins = []
    invalid_ids = []
    already_admins = []

    for arg in context.args:
        try:
            user_id = int(arg)
            if user_id in admins:
                already_admins.append(str(user_id))
            else:
                new_admins.append(user_id)
        except ValueError:
            invalid_ids.append(arg)

    if new_admins:
        admins.extend(new_admins)
        save_admins(admins)
        new_admins_str = ", ".join(str(id) for id in new_admins)
        response = f"✅ Added new admins: {new_admins_str}\n"
    else:
        response = ""

    if invalid_ids:
        invalid_str = ", ".join(invalid_ids)
        response += f"❌ Invalid IDs (must be numbers): {invalid_str}\n"

    if already_admins:
        existing_str = ", ".join(already_admins)
        response += f"⚠️ Already admins: {existing_str}"

    await update.message.reply_text(response or "No valid admin IDs provided.")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove an admin"""
    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return

    try:
        admin_to_remove = int(context.args[0])
        if admin_to_remove in admins:
            admins.remove(admin_to_remove)
            save_admins(admins)
            await update.message.reply_text(f"✅ Removed admin {admin_to_remove}")
        else:
            await update.message.reply_text("⚠️ User is not an admin")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all admins"""
    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    admin_list = "\n".join(str(admin) for admin in admins)
    await update.message.reply_text(f"👑 Admins:\n{admin_list}")

async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the notification group ID"""
    global group_id  # <-- Move this to the top

    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /setgroup <group_id>\n"
            "Example: /setgroup -1001234567890\n\n"
            f"Current group ID: {group_id}"
        )
        return

    try:
        new_group_id = int(context.args[0])
        save_group_id(new_group_id)
        group_id = new_group_id
        await update.message.reply_text(f"✅ Notification group set to: {new_group_id}")
    except ValueError:
        await update.message.reply_text("❌ Group ID must be an integer (include the - for supergroups)")

async def show_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current notification group ID"""
    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    await update.message.reply_text(f"Current notification group ID: {group_id}")

def main():
    app = ApplicationBuilder().token("7770857293:AAFnv-XVnnwE9Qvcxh2gQ8FALwAq21OLJuM").build()

    # Conversation handlers
    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register)],
        states={
            WAITING_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plate)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    customer_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAITING_PLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plate)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Register handlers
    app.add_handler(reg_conv_handler)
    app.add_handler(customer_conv_handler)
    app.add_handler(CommandHandler('ready', ready))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('addadmin', add_admin))
    app.add_handler(CommandHandler('removeadmin', remove_admin))
    app.add_handler(CommandHandler('listadmins', list_admins))
    app.add_handler(CommandHandler('setgroup', set_group))
    app.add_handler(CommandHandler('showgroup', show_group))
    
    print("🚗 Speed Car Wash bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()