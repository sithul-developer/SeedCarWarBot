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
# Constants

ADMIN_FILE = "admins.json"  # File to store admin IDs
GROUP_FILE = "group_id.json"
DEFAULT_ADMINS = [5742761331,509847275]  # Your initial admin ID
GROUP_ID = -4813155053
PHONE_REGEX = re.compile(r'^\+?[0-9\s\-]{8,15}$')
PLATE_REGEX = re.compile(r'^[A-Z0-9-]{3,10}$')
# Conversation states
WAITING_PHONE, WAITING_PLATE, WAITING_CUSTOMER = range(3)
# Database
customer_registry = {}  # Format: {phone_number: {"admin_chat": int, "customer_chat": int, "status": str, "plate": str}}
# Helper functions
# (clean_phone_number is already defined above, so this duplicate can be removed)


# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id in admins:
        await update.message.reply_text(
            "👨‍🔧 *Admin Panel - Speed Car Wash*\n\n"
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
        # Try to extract argument from /start <phone> deep link
        phone = None
        if update.message and update.message.text:
            parts = update.message.text.strip().split()
            if len(parts) > 1:
                phone = parts[1]
        if phone and phone in customer_registry:
            customer_chat = update.effective_chat.id

            customer_registry[phone]["customer_chat"] = customer_chat
            customer_registry[phone]["status"] = "waiting"

            await context.bot.send_message(
                chat_id=customer_registry[phone]["admin_chat"],
                text=(
                    f"*✅អតិថិជនបានចុះឈ្មោះតាមរយៈ QR Code ដោយជោគជ័យ*\n\n"
                    f"📱 លេខទូរស័ព្ទ ៖ {phone}\n"
                    f"🚗 លេខផ្លាក ៖ {customer_registry[phone].get('plate', 'មិនមាន')}\n"
                    f"⏳ ស្ថានភាព៖ កំពុងរង់ចាំសេវា\n\n"
                    f"*✅Customer has successfully registered through QR Code*\n\n"
                    f"📱 Phone : {phone}\n"
                    f"🚗 Plate : {customer_registry[phone].get('plate', 'Not provided')}\n"
                    f"⏳ Status : Waiting for service"
                ),
                parse_mode='Markdown'
            )

            await update.message.reply_text(
                f"✅ ការចុះឈ្មោះអតិថិជនបានដោយជោគជ័យ!\n\n"
                f"📱 លេខទូរស័ព្ទ ៖ {phone}\n"
                f"🚗 លេខផ្លាក ៖ {customer_registry[phone].get('plate', 'មិនមាន')}\n\n"
                "អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់។\n\n"
                f"✅ Successful customer registration completed!\n\n"
                f"📱 Phone : {phone}\n"
                f"🚗 Plate : {customer_registry[phone].get('plate', 'Not provided')}\n\n"
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
    if update.effective_user.id not in admins:
        await update.message.reply_text(
            "❌ អ្នកមិនមានសិទ្ធិប្រើបញ្ជានេះទេ។\n"
            "❌ You are not authorized to use this command."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "✅ សូមមផ្ញើលេខទូរស័ព្ទរបស់អតិថិជន\n"
        "✅ Please send the customer's phone number\n\n"
        "Type /cancel to abort."
    )
    return WAITING_PHONE


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    
    if not PHONE_REGEX.match(phone):
        await update.message.reply_text(
            "❌ សូមពិនិត្យទម្រង់លេខទូរស័ព្ទ​​ ឬ​ លេខផ្លាក។\n"
            "❌ Please check the phone number or plate format.\n\n"
            "Type /cancel to abort."
        )
        return WAITING_PHONE
    
    clean_phone = clean_phone_number(phone)
    context.user_data['register_phone'] = clean_phone
    
    await update.message.reply_text(
        "✅ សូមផ្ញើលេខផ្លាករថយន្តឥឡូវនេះ:\n"
        "✅ Now please send the vehicle plate number:"
    )
    return WAITING_PLATE


async def receive_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plate = update.message.text.strip().upper()
    if not PLATE_REGEX.match(plate):
        await update.message.reply_text(
            "❌ សូមពិនិត្យទម្រង់លេខទូរស័ព្ទ​​ ឬ​ លេខផ្លាក។\n"
            "❌ Please check the phone number or plate format.\n\n"
            "Type /cancel to abort.",
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
        "✅ បានចុះឈ្មោះអតិថិជនថ្មីរួចរាល់ \n\n"
        f"📱 លេខទូរស័ព្ទ : {clean_phone}\n"
        f"🚗 លេខផ្លាក : {plate}\n\n"
        "1. បង្ហាញកូដ QR នេះទៅអតិថិជន\n"
        "2. អតិថិជនស្កែនវាតាមម៉ាស៊ីនថតទូរស័ព្ទ\n"
        "3. ពួកគេនឹងត្រូវបានចុះឈ្មោះដោយស្វ័យប្រវត្តិ\n"
        "ឬផ្ញើតំណផ្ទាល់នេះទៅពួកគេ:\n"
        f"{deep_link}\n\n"
        "✅ New customer registration completed\n\n"
        f"📱 Phone : {clean_phone}\n"
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
        f"✅ បានចុះឈ្មោះអតិថិជនថ្មីរួចរាល់\n\n"
        f"📱 លេខទូរស័ព្ទ : {clean_phone}\n"
        f"🚗 លេខផ្លាក : {customer_registry[clean_phone].get('plate', 'មិនមាន')}\n"
        f"⏳ ស្ថានភាព : កំពុងរង់ចាំសេវា\n\n"
        f"✅ New customer registration completed\n\n"
        f"📱 Phone : {clean_phone}\n"
        f"🚗 Plate : {customer_registry[clean_phone].get('plate', 'Not provided')}\n"
        f"⏳ Status: Waiting for service"
    )
    
    customer_message = (
        f"✅ អតិថិជនបានចុះឈ្មោះជោគជ័យ!!\n\n"
        f"📱 លេខទូរស័ព្ទ : {clean_phone}\n"
        f"🚗 លេខផ្លាក : {customer_registry[clean_phone].get('plate', 'មិនមាន')}\n\n"
        "អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់។\n\n"
        f"*✅ Customer registered successfully!!*\n\n"
        f"📱 Phone : {clean_phone}\n"
        f"🚗 Plate : {customer_registry[clean_phone].get('plate', 'Not provided')}\n\n"
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
    if update.effective_user.id not in admins:
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
        "📢 ជ្រើសរើសអតិថិជនដើម្បីជូនដំណឹង (លេខទូរស័ព្ទ - ផ្លាកលេខ):\n"
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
                f"✨ *ជំរាបសួរ! រថយន្តរបស់លោកអ្នកត្រូវបានលាងសំអាតរួចរាល់ហើយ។ !* ✨\n\n"
                f"📱 លេខទូរស័ព្ទ : {phone}\n"
                f"🚗 លេខផ្លាក : {plate}\n\n"
                "សូមអរគុណសម្រាប់ការរង់ចាំ និងការជឿទុកចិត្តលើសេវាកម្មរបស់យើងខ្ញុំ។ 🚗✨\n\n"
                "✨ *Dear valued customer! Your car has been washed and is now ready.* ✨\n\n"
                f"📱 Phone : {phone}\n"
                f"🚗 Plate : {plate}\n\n"
                "Thank you for your patience and trust in our service."
                ),
                parse_mode='Markdown'
            )
            await context.bot.send_message(
                chat_id=customer_data["admin_chat"],
                text=(
                f"✅ បានជូនដំណឹងអតិថិជនដោយជោគជ័យថារថយន្តរួចរាល់\n\n"
                f"📱 លេខទូរស័ព្ទ : {phone}\n"
                f"🚗 លេខផ្លាក : {plate}\n\n"
                f"✅ Successfully notified customer that car is ready\n\n"
                f"📱 Phone : {phone}\n"
                f"🚗 Plate : {plate}\n\n"
                ),
                parse_mode='Markdown'
            )
            customer_registry[phone]["status"] = "ready"
        else:
            await query.edit_message_text(
                "❌ រកមិនឃើញអតិថិជនទេ\n"
                "❌ Could not find customer."
            )


""" async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is authorized
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "❌ អ្នកមិនមានសិទ្ធិប្រើបញ្ជានេះទេ។\n"
            "❌ You are not authorized to use this command."
        )
        return
    
    # Check if registry is empty
    if not customer_registry:
        await update.message.reply_text(
            "ℹ️ គ្មានអតិថិជនណាត្រូវបានចុះឈ្មោះនៅពេលបច្ចុប្បន្នទេ។\n"
            "ℹ️ No customers currently registered."
        )
        return
    
    # Build status message
    status_message = (
        "*បច្ចុប្បន្នការចុះឈ្មោះរួចរាល់ ✅*\n"
        "*Current Registrations ✅*\n\n"
    )
    
    for phone, data in customer_registry.items():
        status_message += (
            f"📱 *លេខទូរស័ព្ទ :* {phone}\n"
            f"🚗 *លេខផ្លាក :* {data.get('plate', 'មិនមាន')}\n"
            f"⏳ *ស្ថានភាព :* {data.get('status', 'មិនស្គាល់')}\n"
            f"👨‍🔧 *អតិថិជន :* {'បានចុះឈ្មោះ' if data.get('customer_chat', False) else 'កំពុងរង់ចាំ'}\n\n"
            f"📱 *Phone :* {phone}\n"
            f"🚗 *Plate :* {data.get('plate', 'Not provided')}\n"
            f"⏳ *Status :* {data.get('status', 'unknown')}\n"
            f"👨‍🔧 *Customer:* {'registered' if data.get('customer_chat', False) else 'pending'}\n\n"
        )
    
    # Send the message based on update type
    try:
        if update.message:
            await update.message.reply_text(status_message, parse_mode='Markdown')
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.message.reply_text(status_message, parse_mode='Markdown')
    except Exception as e:
        print(f"Error sending status message: {e}")
 """
# Admin management functions
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
                # If the file is corrupted or not a list, reset to default
                raise ValueError("Admin file is not a list")
        except (json.JSONDecodeError, ValueError, IOError, TypeError):
            # Remove the corrupted file so it can be recreated
            try:
                os.remove(ADMIN_FILE)
            except Exception:
                pass  # Ignore errors during file removal

    # Create file with default admins if doesn't exist or is invalid
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

# Initialize admins
admins = load_admins()

# Helper functions
def clean_phone_number(phone: str) -> str:
    """Normalize phone number by removing all non-digit characters"""
    return ''.join(c for c in phone if c.isdigit())

# Admin management commands
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

    # Process valid new admins
    if new_admins:
        admins.extend(new_admins)
        save_admins(admins)
        new_admins_str = ", ".join(str(id) for id in new_admins)
        response = f"✅ Added new admins: {new_admins_str}\n"
    else:
        response = ""

    # Add warnings for invalid/duplicate IDs
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
                # Accept int, string, or dict with 'group_id'
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
                    # If the file is corrupted or not a valid group id, reset to None
                    return None
    except (json.JSONDecodeError, IOError):
        pass
    return None

def save_group_id(group_id):
    """Save group ID to file"""
    with open(GROUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(group_id, f)

# Initialize group_id
group_id = load_group_id() or GROUP_ID  # Fallback to original GROUP_ID if not set
async def set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the notification group ID"""
    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /setgroup <group_id>\n"
            "Example: /setgroup -1001234567890\n\n"
            "Current group ID: {group_id}"
        )
        return

    try:
        global group_id
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ប្រតិបត្តិការត្រូវបានបោះបង់។\n"
        "Operation cancelled."
    )
    return ConversationHandler.END
# Add this handler function with the other command handlers
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
            "2. Provide your phone number when asked\n"
            "3. You'll be notified when your car is ready\n\n"
            "សូមអរគុណសម្រាប់ការប្រើប្រាស់សេវាកម្មរបស់យើង។\n"
            "ដើម្បីចុះឈ្មោះទទួលការជូនដំណឹង៖\n"
            "1. បញ្ជូនពាក្យបញ្ជា /start\n"
            "2. ផ្ញើលេខទូរស័ព្ទរបស់អ្នកនៅពេលស្នើសុំ\n"
            "3. អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់"
        )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    app = ApplicationBuilder().token("7542010152:AAHNUnrAXmOgXt3SG6pJVSzU6ArMMurzquw").build() #chat id on production #7542010152:AAHNUnrAXmOgXt3SG6pJVSzU6ArMMurzquw

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