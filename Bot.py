
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
    ConversationHandler,
)
import re
import json
import os
import time
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file if present
TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.environ.get("PORT", 5000))
# Constants
ADMIN_FILE = "admins.json"  # File to store admin IDs
DEFAULT_ADMINS = [5742761331]  # Your initial admin IDs
DEFAULT_SUBGROUP_ID = -1002210878700  # Your subgroup ID -1002210878700_33970
MESSAGE_THREAD_ID = 33970
PLATE_REGEX = re.compile(r"^[A-Z0-9-]{3,10}$")

# Conversation states
WAITING_PLATE, WAITING_CUSTOMER = range(2)

customer_registry = {}  # Dictionary to store customer data
queue_counter = 1  # Initialize queue counter


def clean_old_entries():
    """Remove entries older than 7 days"""
    global customer_registry

    current_time = datetime.now()
    seven_days_ago = current_time - timedelta(days=7)

    # Create list of keys to delete
    to_delete = [
        queue_num
        for queue_num, data in customer_registry.items()
        if datetime.strptime(data["timestamp"], "%Y-%m-%d %H:%M:%S") < seven_days_ago
    ]

    # Delete old entries
    for queue_num in to_delete:
        del customer_registry[queue_num]

    if to_delete:
        print(f"Cleaned up {len(to_delete)} old entries from customer registry")


def scheduled_cleanup():
    """Run cleanup every 24 hours"""
    while True:
        clean_old_entries()
        time.sleep(24 * 60 * 60)  # Sleep for 24 hours


# Start the cleanup thread when your application starts
cleanup_thread = threading.Thread(target=scheduled_cleanup)
cleanup_thread.daemon = True
cleanup_thread.start()


def generate_queue_number():
    """Generate a unique queue number with date prefix"""
    global queue_counter
    today = datetime.now().strftime("%Y%m%d")
    queue_number = f"{today}-{queue_counter:03d}"
    queue_counter += 1

    # Ensure timestamp is added to new entries
    customer_registry[queue_number] = {
        **customer_registry.get(queue_number, {}),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    return queue_number


def load_admins():
    """Load admin IDs from file or create with default if not exists"""
    if os.path.exists(ADMIN_FILE):
        try:
            with open(ADMIN_FILE, "r", encoding="utf-8") as f:
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
        with open(ADMIN_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_ADMINS, f)
    except Exception as e:
        print(f"Error writing admin file: {e}")
    return DEFAULT_ADMINS


def save_admins(admin_list):
    """Save admin IDs to file"""
    with open(ADMIN_FILE, "w", encoding="utf-8") as f:
        json.dump(admin_list, f)


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add one or multiple admins at once"""
    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "• Add single admin: `/addadmin 123456789`\n"
            "• Add multiple admins: /addadmin 123456789 987654321 555555555"
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

    removed_admins = []
    invalid_ids = []
    not_admins = []

    for arg in context.args:
        try:
            user_id = int(arg)
            if user_id in admins:
                admins.remove(user_id)
                removed_admins.append(str(user_id))
            else:
                not_admins.append(str(user_id))
        except ValueError:
            invalid_ids.append(arg)

    if removed_admins:
        save_admins(admins)
        response = f"✅ Removed admins: {', '.join(removed_admins)}\n"
    else:
        response = ""

    if invalid_ids:
        response += f"❌ Invalid IDs (must be numbers): {', '.join(invalid_ids)}\n"
    if not_admins:
        response += f"⚠️ Not admins: {', '.join(not_admins)}"

    await update.message.reply_text(response or "No valid admin IDs provided.")


async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all admin user IDs"""
    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return
    if not admins:
        await update.message.reply_text("No admins are currently set.")
    else:
        await update.message.reply_text(
            "Current admins:\n" + "\n".join(f"• {admin_id}" for admin_id in admins)
        )


admins = load_admins()


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
            parse_mode="Markdown",
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

            # Message to admin
            admin_message = (
                f"អតិថិជនបានចុះឈ្មោះតាមរយៈ QR Code ដោយជោគជ័យ\n\n"
                f"🛂 លេខសំបុត្រ# : {queue_number}\n"
                f"🚗 ផ្លាកលេខ : {customer_registry[queue_number].get('plate', 'មិនមាន')}\n"
                f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n"
                f"⏳ ស្ថានភាព៖ កំពុងរង់ចាំសេវាកម្ម\n\n"
                f"Customer has successfully registered through QR Code\n\n"
                f"🛂 Ticket number# : {queue_number}\n"
                f"🚗 Plate : {customer_registry[queue_number].get('plate', 'Not provided')}\n"
                f"👤 Customer Name : {update.effective_user.full_name}\n"
                f"⏳ Status : Waiting for service"
            )

            await context.bot.send_message(
                chat_id=customer_registry[queue_number]["admin_chat"],
                text=admin_message,
                parse_mode="Markdown",
            )

            # Message to subgroup (in the specified thread)
            if DEFAULT_SUBGROUP_ID and MESSAGE_THREAD_ID:
                try:
                    await context.bot.send_message(
                        chat_id=DEFAULT_SUBGROUP_ID,
                        message_thread_id=MESSAGE_THREAD_ID,
                        text=(
                            f"អតិថិជនបានចុះឈ្មោះតាមរយៈ QR Code ដោយជោគជ័យ\n\n"
                            f"🛂 លេខសំបុត្រ# : {queue_number}\n"
                            f"🚗 ផ្លាកលេខ : {customer_registry[queue_number].get('plate', 'មិនមាន')}\n"
                            f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n"
                            f"⏳ ស្ថានភាព៖ កំពុងរង់ចាំសេវាកម្ម\n"
                            f"⏰ ពេលវេលា: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                            f"Customer has successfully registered through QR Code\n\n"
                            f"🛂 Ticket number# : {queue_number}\n"
                            f"🚗 Plate : {customer_registry[queue_number].get('plate', 'Not provided')}\n"
                            f"👤 Customer Name : {update.effective_user.full_name}\n"
                            f"⏳ Status : Waiting for service\n"
                            f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    print(f"Error sending registration notification to subgroup: {e}"),

            await update.message.reply_text(
                f"ការចុះឈ្មោះអតិថិជនបានដោយជោគជ័យ!\n\n"
                f"🛂 លេខសំបុត្រ# : {queue_number}\n"
                f"🚗 ផ្លាកលេខ : {customer_registry[queue_number].get('plate', 'មិនមាន')}\n"
                f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n\n"
                "អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់។\n\n"
                f"Successful customer registration completed!\n\n"
                f"🛂 Titke Number : {queue_number}\n"
                f"🚗 Plate : {customer_registry[queue_number].get('plate', 'Not provided')}\n"
                f"👤 Customer Name : {update.effective_user.full_name}\n\n"
                "You'll be notified when your car is ready.",
                parse_mode="Markdown",
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
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            context.user_data["queue_number"] = queue_number

            await update.message.reply_text(
                "🚗 *សូមស្វាគមន៍មកកាន់ Speed Car Wash!*\n\n"
                "សូមផ្ញើផ្លាកលេខរថយន្តរបស់អ្នក។\n"
                "ឧទាហរណ៍៖ ABC-1234\n\n"
                "🚗 *Welcome to Speed Car Wash!*\n\n"
                "Please send your vehicle plate number.\n"
                "Example: ABC-1234",
                parse_mode="Markdown",
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
            parse_mode="Markdown",
        )
        return WAITING_PLATE

    # Check if plate exists in registry
    for existing_data in customer_registry.values():
        if existing_data.get("plate") == plate:
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
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "customer_name": update.effective_user.full_name,
        }

        # Generate QR code
        bot_username = (await context.bot.get_me()).username
        deep_link = f"https://t.me/{bot_username}?start={queue_number}"

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
        bio.name = "qr_code.png"
        img.save(bio, "PNG")
        bio.seek(0)

        caption = (
            "បានចុះឈ្មោះអតិថិជនថ្មីរួចរាល់ \n\n"
            f"🛂 លេខសំបុត្រ# : {queue_number}\n"
            f"🚗 ផ្លាកលេខ : {plate}\n\n"
            "1. បង្ហាញកូដ QR នេះទៅអតិថិជន\n"
            "2. អតិថិជនស្កែនវាតាមម៉ាស៊ីនថតទូរស័ព្ទ\n"
            "3. ពួកគេនឹងត្រូវបានចុះឈ្មោះដោយស្វ័យប្រវត្តិ\n"
            "ឬផ្ញើតំណផ្ទាល់នេះទៅពួកគេ:\n"
            f"{deep_link}\n\n"
            "New customer registration completed\n\n"
            f"🛂 Ticket Number : {queue_number}\n"
            f"🚗 Plate : {plate}\n\n"
            "1. Show this QR code to the customer\n"
            "2. They scan it with their phone camera\n"
            "3. They'll be automatically registered\n"
            "Or send them this direct link:\n"
            f"{deep_link}"
        )

        await update.message.reply_photo(photo=bio, caption=caption)

    else:  # Customer self-registration flow
        queue_number = context.user_data.get("queue_number")
        customer_registry[queue_number].update(
            {
                "plate": plate,
                "status": "waiting",
                "customer_name": update.effective_user.full_name,
                "customer_chat": update.effective_chat.id,
            }
        )

        # Notify customer
        await update.message.reply_text(
            f"ការចុះឈ្មោះអតិថិជនបានដោយជោគជ័យ!\n\n"
            f"🛂 លេខសំបុត្រ# : {queue_number}\n"
            f"🚗 ផ្លាកលេខ : {plate}\n"
            f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n\n"
            "អ្នកនឹងទទួលបានការជូនដំណឹងនៅពេលរថយន្តរបស់អ្នករួចរាល់។\n\n"
            f"Successful customer registration completed!\n\n"
            f"🛂 Ticket Number : {queue_number}\n"
            f"🚗 Plate : {plate}\n"
            f"👤 Customer Name : {update.effective_user.full_name}\n\n"
            "You'll be notified when your car is ready.",
            parse_mode="Markdown",
        )

        # Send notification to admin
        if admins:
            admin_chat = customer_registry[queue_number]["admin_chat"]
            if not admin_chat:
                # If admin chat is not set, use the first admin
                admin_chat = admins[0]
                customer_registry[queue_number]["admin_chat"] = admin_chat

            try:
                await context.bot.send_message(
                    chat_id=admin_chat,
                    text=(
                        f"អតិថិជនបានចុះឈ្មោះដោយខ្លួនឯងដោយជោគជ័យ\n\n"
                        f"🛂 លេខសំបុត្រ# : {queue_number}\n"
                        f"🚗 ផ្លាកលេខ : {plate}\n"
                        f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n"
                        f"⏳ ស្ថានភាព៖ កំពុងរង់ចាំសេវាកម្ម\n\n"
                        f"*Customer has self-registered successfully*\n\n"
                        f"🛂 Ticket Number : {queue_number}\n"
                        f"🚗 Plate : {plate}\n"
                        f"👤 Customer Name : {update.effective_user.full_name}\n"
                        f"⏳ Status : Waiting for service\n\n"
                    ),
                    parse_mode="Markdown",
                )

            except Exception as e:
                print(f"Failed to notify admin {admin_chat}: {e}")
        # Send notification to subgroup
        if DEFAULT_SUBGROUP_ID and MESSAGE_THREAD_ID:
            await context.bot.send_message(
                chat_id=DEFAULT_SUBGROUP_ID,
                message_thread_id=MESSAGE_THREAD_ID,
                text=(
                    f"អតិថិជនបានចុះឈ្មោះដោយខ្លួនឯងដោយជោគជ័យ\n\n"
                    f"🛂 លេខសំបុត្រ# : {queue_number}\n"
                    f"🚗 ផ្លាកលេខ : {plate}\n"
                    f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n"
                    f"⏳ ស្ថានភាព៖ កំពុងរង់ចាំសេវាកម្ម\n"
                    f"⏰ ពេលវេលា: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"Customer has self-registered successfully\n\n"
                    f"🛂 Ticket Number: {queue_number}\n"
                    f"🚗 Plate: {plate}\n"
                    f"👤 Customer: {update.effective_user.full_name}\n"
                    f"⏳ Status: Waiting for service\n"
                    f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                ),
                parse_mode="Markdown",
            )

        # Update customer data
        customer_registry[queue_number]["customer_chat"] = update.effective_user.id

    return ConversationHandler.END


async def ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admins:
        await update.message.reply_text(
            "❌ អ្នកមិនមានសិទ្ធិប្រើបញ្ជានេះទេ។\n"
            "❌ You are not authorized to use this command."
        )
        return

    ready_customers = {
        qn: data
        for qn, data in customer_registry.items()
        if data["customer_chat"] and data["status"] == "waiting"
    }

    if not ready_customers:
        await update.message.reply_text(
            "🚫 គ្មានអតិថិជនណាកំពុងរង់ចាំការជូនដំណឹងទេ។\n"
            "🚫 No customers currently waiting for notification."
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                f"{qn} ({data.get('plate', 'No plate')})", callback_data=f"ready_{qn}"
            )
        ]
        for qn, data in ready_customers.items()
    ]

    await update.message.reply_text(
        "📢 ជ្រើសរើសអតិថិជនដើម្បីជូនដំណឹង (លេខសំបុត្រ# - ផ្លាកលេខ):\n"
        "📢 Select customer to notify ( Ticket Number - Plate):",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def format_status(queue_number, data):
    """Format status information for display with bilingual support"""
    status_mapping = {
        "pending": ("⏳ Pending registration", "⏳ កំពុងរង់ចាំចុះឈ្មោះ"),
        "waiting": ("🛠 In progress (waiting)", "🛠 កំពុងធ្វើការ (រង់ចាំ)"),
        "ready": ("✅ Ready for pickup", "✅ រួចរាល់សម្រាប់ទទួល"),
        "registered": (
            "📝 Registered (waiting for customer)",
            "📝 បានចុះឈ្មោះ (រង់ចាំអតិថិជន)",
        ),
    }

    status_en, status_kh = status_mapping.get(
        data.get("status", "pending"),
        (data.get("status", "pending"), data.get("status", "pending")),
    )

    message = (
        f"👤 *ឈ្មោះអតិថិជន / Customer*: {data.get('customer_name', 'មិនមាន / None')}\n"
        f"🛂 *លេខសំបុត្រ / Ticket*: `{queue_number}`\n"
        f"🚗 *ផ្លាកលេខ / Plate*: {data.get('plate', 'មិនមាន / None')}\n"
        f"📊 *ស្ថានភាព / Status*: {status_kh} / {status_en}\n"
        f"🕒 *ពេលវេលាចុះឈ្មោះ / Registered*: {data.get('timestamp', 'មិនស្គាល់ / Unknown')}\n\n"
    )
    return message


async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check the status of a car wash registration"""
    user_id = update.effective_user.id

    # Check if user provided a queue number
    if context.args:
        queue_number = context.args[0]
        if queue_number in customer_registry:
            data = customer_registry[queue_number]

            # Check if user is authorized (either admin, or the customer who registered)
            if user_id in admins or data.get("customer_chat") == user_id:
                await update.message.reply_text(
                    format_status(queue_number, data), parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "❌ You are not authorized to view this ticket.\n"
                    "❌ អ្នកមិនមានសិទ្ធិមើលសំបុត្រនេះទេ។"
                )
        else:
            await update.message.reply_text(
                "❌ Ticket number not found.\n" "❌ រកមិនឃើញលេខសំបុត្រនេះទេ។"
            )
        return

    # If no queue number provided, show all relevant tickets
    if user_id in admins:
        # Admin sees all tickets
        relevant_tickets = customer_registry.items()
        header = (
            "👑 *Admin View - All Tickets* 👑\n"
            "👑 *ទិដ្ឋភាពអ្នកគ្រប់គ្រង - សំបុត្រទាំងអស់* 👑\n\n"
        )
    else:
        # Customer sees only their tickets
        relevant_tickets = [
            (qn, data)
            for qn, data in customer_registry.items()
            if data.get("customer_chat") == user_id
        ]
        header = "🚗 *Your Car Wash Tickets* 🚗\n" "🚗 *សំបុត្រលាងរថយន្តរបស់អ្នក* 🚗\n\n"

    if not relevant_tickets:
        await update.message.reply_text("ℹ️ No tickets found.\n" "ℹ️ មិនមានសំបុត្រណាមួយទេ។")
        return

    # Prepare message parts
    message_parts = [header]

    for queue_number, data in relevant_tickets:
        status_text = format_status(queue_number, data)
        if len("\n\n".join(message_parts) + "\n\n" + status_text) > 4000:
            # Send current parts if adding this would exceed limit
            await update.message.reply_text(
                "\n\n".join(message_parts), parse_mode="Markdown"
            )
            message_parts = [header]  # Start new message with header

        message_parts.append(status_text)

    # Send remaining messages
    for i, part in enumerate(message_parts):
        if i == 0 and len(message_parts) > 1:
            continue  # Skip header if it's not the only part
        await update.message.reply_text(part, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("ready_"):
        queue_number = query.data[6:]
        customer_data = customer_registry.get(queue_number)

        if customer_data and customer_data["customer_chat"]:
            plate = customer_data.get("plate", "unknown plate")
            staff_name = update.effective_user.full_name
            # Message to customer
            await context.bot.send_message(
                chat_id=customer_data["customer_chat"],
                text=(
                    f"✨ *ជំរាបសួរ! រថយន្តរបស់លោកអ្នកត្រូវបានលាងសំអាតរួចរាល់ហើយ។ !* ✨\n\n"
                    f"🛂 លេខសំបុត្រ# : {queue_number}\n"
                    f"🚗 ផ្លាកលេខ : {plate}\n\n"
                    "សូមអរគុណសម្រាប់ការរង់ចាំ និងការជឿទុកចិត្តលើសេវាកម្មរបស់យើងខ្ញុំ។ 🚗✨\n\n"
                    "✨ *Dear valued customer! Your car has been washed and is now ready.* ✨\n\n"
                    f"🛂 Ticket Number : {queue_number}\n"
                    f"🚗 Plate : {plate}\n"
                    "Thank you for your patience and trust in our service."
                ),
                parse_mode="Markdown",
            )

            # Message to admin
            await context.bot.send_message(
                chat_id=customer_data["admin_chat"],
                text=(
                    f"📢 បានជូនដំណឹងអតិថិជនដោយជោគជ័យ\n\n"
                    f"🛂 លេខសំបុត្រ# : {queue_number}\n"
                    f"🚗 ផ្លាកលេខ : {plate}\n"
                    f"👤 ឈ្មោះបុគ្គលិក : {staff_name}\n\n"
                    f"📢 Successfully notified customer\n\n"
                    f"🛂 Ticket Number : {queue_number}\n"
                    f"🚗 Plate : {plate}\n"
                    f"👤 Staff Name : {staff_name}\n\n"
                ),
                parse_mode="Markdown",
            )

            # Message to subgroup (in the specified thread)
            try:
                await context.bot.send_message(
                    chat_id=DEFAULT_SUBGROUP_ID,
                    message_thread_id=MESSAGE_THREAD_ID,
                    text=(
                        f"អតិថិជនត្រូវបានជូនដំណឹងថារថយន្តរបស់គាត់រួចរាល់។\n\n"
                        f"🛂 លេខសំបុត្រ : {queue_number}\n"
                        f"🚗 ផ្លាកលេខ : {plate}\n"
                        f"👤 ឈ្មោះបុគ្គលិក : {staff_name}\n"
                        f"⏰ ពេលវេលា: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"The customer has been notified that their car is ready\n\n"
                        f"🛂 Ticket Number: {queue_number}\n"
                        f"🚗 Plate: {plate}\n"
                        f"👤 Staff Name: {staff_name}\n"
                        f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                print(f"Error sending message to subgroup: {e}")
                # Optionally notify admin about the failure
                await context.bot.send_message(
                    chat_id=customer_data["admin_chat"],
                    text=f"⚠️ Failed to send notification to subgroup: {e}",
                )

            customer_registry[queue_number]["status"] = "ready"

        else:
            await query.edit_message_text(
                "❌ រកមិនឃើញអតិថិជនទេ\n" "❌ Could not find customer."
            )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ប្រតិបត្តិការត្រូវបានបោះបង់។\n" "Operation cancelled.")
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admins:
        help_text = (
            "🛠 *Speed Car Wash Bot Help* 🛠\n\n"
            "*Admin Commands:*\n"
            "/register - Register a new customer\n"
            "/ready - Notify customer their car is ready\n"
            "/cancel - Cancel current operation\n"
            "/status - Check your wash status\n\n"
            "*Customer Commands:*\n"
            "/start - Begin registration process\n\n"
            "*General Commands:*\n"
            "/help - Show this help message\n\n"
            "ជំនួយសម្រាប់ប្រព័ន្ធលាងរថយន្ត Speed Car Wash\n"
            "ពាក្យបញ្ជាសម្រាប់អ្នកគ្រប់គ្រង៖\n"
            "/register - ចុះឈ្មោះអតិថិជនថ្មី\n"
            "/ready - ជូនដំណឹងអតិថិជនថារថយន្តរួចរាល់\n"
            "/cancel - បោះបង់ប្រតិបត្តិការបច្ចុប្បន្ន\n"
            "/status - ពិនិត្យស្ថានភាព\n\n"
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

    await update.message.reply_text(help_text, parse_mode="Markdown")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register)],
        states={
            WAITING_PLATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plate)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    customer_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_PLATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_plate)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Register handlers
    app.add_handler(reg_conv_handler)
    app.add_handler(customer_conv_handler)
    app.add_handler(CommandHandler("ready", ready))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("status", check_status))
    app.add_handler(CommandHandler("listadmins", list_admins))
    app.add_handler(CommandHandler("cancel", cancel))

    app.run_polling()


if __name__ == "__main__":
    main()
