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
# Constants
ADMIN_FILE = "admins.json"  # File to store admin IDs
GROUP_FILE = "group_ids.json"
DEFAULT_ADMINS = [5742761331]  # Your initial admin IDs 509847275
DEFAULT_GROUPS = ["-1002210878700_33970"]  # Default group ID for notifications
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


# Start the cleanup thread when your application starts
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


# Load admin IDs from file or create with default if not exists
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


# Save admin IDs to file
def save_admins(admin_list):
    """Save admin IDs to file"""
    with open(ADMIN_FILE, "w", encoding="utf-8") as f:
        json.dump(admin_list, f)


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


# Remove an admin
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


# List all admin user IDs
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


# Load group ID from file or return None if not set
def load_group_id():
    """Load group ID from file or return None if not set"""
    try:
        if os.path.exists(GROUP_FILE):
            with open(GROUP_FILE, "r", encoding="utf-8") as f:
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


# Save group ID to file
def save_group_id(group_id):
    """Save group ID to file"""
    with open(GROUP_FILE, "w", encoding="utf-8") as f:
        json.dump(group_id, f)


admins = load_admins()
group_id = load_group_id() or DEFAULT_GROUPS[0]


# List to store multiple group IDs, loaded from file
def load_group_ids():
    """Load group IDs from persistent storage"""
    try:
        if os.path.exists(GROUP_FILE):
            with open(GROUP_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                data = json.loads(content)
                if isinstance(data, list):
                    return data
                elif isinstance(data, (int, str)):
                    return [int(data)]
                else:
                    return []
    except (json.JSONDecodeError, IOError, ValueError, TypeError):
        pass
    return []


group_ids = load_group_ids()  # List to store multiple group IDs, loaded from file


# Define the main application
def save_group_ids(group_ids):
    """Save group IDs to persistent storage"""
    with open(GROUP_FILE, "w", encoding="utf-8") as f:
        json.dump(group_ids, f)


async def addgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add one or more notification group IDs"""
    global group_ids

    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /addgroups <group_id1> <group_id2> ...\n"
            "Example: /addgroups -1001234567890 -1009876543210\n\n"
            f"Current groups: {', '.join(map(str, group_ids)) if group_ids else 'None'}"
        )
        return

    added_groups = []
    already_exists = []
    invalid = []

    for arg in context.args:
        try:
            new_group_id = int(arg)
            if new_group_id in group_ids:
                already_exists.append(str(new_group_id))
            else:
                group_ids.append(new_group_id)
                added_groups.append(str(new_group_id))
        except ValueError:
            invalid.append(arg)

    save_group_ids(group_ids)

    response = []
    if added_groups:
        response.append(f"✅ Added groups: {', '.join(added_groups)}")
    if already_exists:
        response.append(f"ℹ️ Already exists: {', '.join(already_exists)}")
    if invalid:
        response.append(f"❌ Invalid IDs (must be integers): {', '.join(invalid)}")

    await update.message.reply_text("\n".join(response))


# List all notification group IDs
async def listgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all notification group IDs"""
    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    if not group_ids:
        await update.message.reply_text("No notification groups are currently set.")
    else:
        await update.message.reply_text(
            "Current notification groups:\n"
            + "\n".join(f"• {gid}" for gid in group_ids)
        )


# Remove a notification group ID
async def removegroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a notification group ID"""
    global group_ids

    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /removegroup <group_id>\n"
            "Example: /removegroup -1001234567890\n\n"
            f"Current groups: {', '.join(map(str, group_ids)) if group_ids else 'None'}"
        )
        return

    try:
        group_to_remove = int(context.args[0])
        if group_to_remove in group_ids:
            group_ids.remove(group_to_remove)
            save_group_ids(group_ids)
            await update.message.reply_text(f"✅ Removed group: {group_to_remove}")
        else:
            await update.message.reply_text(
                f"❌ Group ID {group_to_remove} not found in the list."
            )
    except ValueError:
        await update.message.reply_text(
            "❌ Group ID must be an integer (include the - for supergroups)"
        )


# Save group IDs to persistent storage
def save_group_ids(group_ids):
    """Save group IDs to persistent storage"""
    with open(GROUP_FILE, "w", encoding="utf-8") as f:
        json.dump(group_ids, f)


# Start the bot and define command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    GROUP_CHAT_ID = (
        group_ids[0] if group_ids else DEFAULT_GROUPS[0]
    )  # Use group_ids if set, else fallback

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

            # Send to all group_ids if available, else fallback to DEFAULT_GROUPS
            target_groups = group_ids if group_ids else DEFAULT_GROUPS
            for gid in target_groups:
                try:
                    await context.bot.send_message(
                        chat_id=gid, text=admin_message, parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Failed to send message to group {gid}: {e}")

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


# Register command handler
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


# Register the conversation handler
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

        # Define group_message before sending to groups
        group_message = (
            f"*អតិថិជនថ្មីត្រូវបានចុះឈ្មោះដោយបុគ្គលិក*\n\n"
            f"🛂 លេខសំបុត្រ# : {queue_number}\n"
            f"🚗 ផ្លាកលេខ : {plate}\n"
            f"👤 ឈ្មោះអតិថិជន : {update.effective_user.full_name}\n"
            f"⏳ ស្ថានភាព៖ កំពុងរង់ចាំអតិថិជនបញ្ចូលតាម QR\n\n"
            f"*A new customer has been registered by staff*\n\n"
            f"🛂 Ticket Number : {queue_number}\n"
            f"🚗 Plate : {plate}\n"
            f"👤 Customer Name : {update.effective_user.full_name}\n"
            f"⏳ Status : Waiting for customer to scan QR\n\n"
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
        group_message = (
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
        )
        # Notify Groups
        if DEFAULT_GROUPS:
            for group_id in DEFAULT_GROUPS:
                try:
                    await context.bot.send_message(
                        chat_id=group_id, text=group_message, parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Failed to send message to group {group_id}: {e}")

        # Send to admin if available, otherwise to all groups
        if admins:
            admin_chat_id = admins[0]  # Primary admin
            customer_registry[queue_number]["admin_chat"] = admin_chat_id

            try:
                await context.bot.send_message(
                    chat_id=admin_chat_id, text=group_message, parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Failed to notify admin {admin_chat_id}: {e}")

                # Fallback to groups if admin notification fails
                if DEFAULT_GROUPS:
                    for group_id in DEFAULT_GROUPS:
                        try:
                            await context.bot.send_message(
                                chat_id=group_id,
                                text=group_message,
                                parse_mode="Markdown",
                            )
                        except Exception as e:
                            print(f"Failed to send message to group {group_id}: {e}")

        elif DEFAULT_GROUPS:  # If no admins, send to all groups
            for group_id in DEFAULT_GROUPS:
                try:
                    await context.bot.send_message(
                        chat_id=group_id, text=group_message, parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"Failed to send message to group {group_id}: {e}")

    return ConversationHandler.END


# Ready command handler
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


# format_status
def format_status(queue_number, data):
    """Format status information for display"""
    status_mapping = {
        "pending": "⏳ Pending registration",
        "waiting": "🛠 In progress (waiting)",
        "ready": "✅ Ready for pickup",
        "registered": "📝 Registered (waiting for customer)",
    }

    status_text = status_mapping.get(
        data.get("status", "pending"), data.get("status", "pending")
    )

    message = (
        f"👑 *Admin View - Ticket Status* 👑\n\n"
        f"👤 *ឈ្មោះអតិថិជន*: {data.get('customer_name', 'មិនមាន')}\n"
        f"🛂 *លេខសំបុត្រ*: `{queue_number}`\n"
        f"🚗 *ផ្លាកលេខ*: {data.get('plate', 'មិនមាន')}\n"
        f"📊 *ស្ថានភាព*: {status_text}\n"
        f"🕒 *ពេលវេលាចុះឈ្មោះ*: {data.get('timestamp', 'មិនស្គាល់')}\n\n"
        f"🛂 *Ticket Number*: `{queue_number}`\n"
        f"🚗 *Plate*: {data.get('plate', 'Not provided')}\n"
        f"📊 *Status*: {status_text}\n"
        f"🕒 *Registered at*: {data.get('timestamp', 'Unknown')}\n\n"
    )
    return message


# Check status command handler
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
        message = "👑 *Admin View - All Tickets* 👑\n\n"
    else:
        # Customer sees only their tickets
        relevant_tickets = [
            (qn, data)
            for qn, data in customer_registry.items()
            if data.get("customer_chat") == user_id
        ]
        message = "🚗 *Your Car Wash Tickets* 🚗\n\n"

    if not relevant_tickets:
        await update.message.reply_text("ℹ️ No tickets found.\n" "ℹ️ មិនមានសំបុត្រណាមួយទេ។")
        return

    for queue_number, data in relevant_tickets:
        message += format_status(queue_number, data) + "\n\n"

    # Split long messages to avoid Telegram's message length limit
    if len(message) > 4000:
        parts = [message[i : i + 4000] for i in range(0, len(message), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")


# Button handler for ready notification
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
                    f"🚗 ផ្លាកលេខ : {plate}\n"
                    f"👤 ឈ្មោះបុគ្គលិក : {staff_name}\n\n"
                    "សូមអរគុណសម្រាប់ការរង់ចាំ និងការជឿទុកចិត្តលើសេវាកម្មរបស់យើងខ្ញុំ។ 🚗✨\n\n"
                    "✨ *Dear valued customer! Your car has been washed and is now ready.* ✨\n\n"
                    f"🛂 Ticket Number : {queue_number}\n"
                    f"🚗 Plate : {plate}\n"
                    f"👤 Staff Name : {staff_name}\n\n"
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

            # Message to all notification groups
            if group_ids:
                for gid in group_ids:
                    try:
                        await context.bot.send_message(
                            chat_id=gid,
                            text=(
                                f"ការលាងសំអាតរថយន្តអតិថិជនត្រូវបានបញ្ចប់ដោយជោគជ័យ។\n\n"
                                f"🛂 លេខសំបុត្រ# : {queue_number}\n"
                                f"🚗 ផ្លាកលេខ : {plate}\n"
                                f"👤 ឈ្មោះបុគ្គលិក : {staff_name}\n\n"
                                f"The customer's car wash has been successfully completed.\n\n"
                                f"🛂 Ticket # : {queue_number}\n"
                                f"🚗 Plate : {plate}\n"
                                f"👤 Staff Name : {staff_name}\n"
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        print(f"Failed to send message to group {gid}: {e}")

            customer_registry[queue_number]["status"] = "ready"

        else:
            await query.edit_message_text(
                "❌ រកមិនឃើញអតិថិជនទេ\n" "❌ Could not find customer."
            )


# Cancel command handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ប្រតិបត្តិការត្រូវបានបោះបង់។\n" "Operation cancelled.")
    return ConversationHandler.END


# Help command handler
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


# Protection function game to ensure only admins can access certain commands

def is_prohibited_message(text: str) -> bool:
    """Check if message contains game/gambling/crypto scam/airdrop keywords"""
    prohibited_keywords = [
        # Game/Gambling keywords
        "game",
        "gamble",
        "bet",
        "casino",
        "lottery",
        "slot",
        "poker",
        "baccarat",
        "roulette",
        "ភ្នាល់",
        "ល្បែង",
        "ស្លត់",
        "បាការ៉ាត់",
        "ឡូតេ",
        # Crypto scam/airdrop keywords
        "airdrop",
        "token",
        "claim free",
        "crypto",
        "web3",
        "defi",
        "wallet connect",
        "connect wallet",
        "snapshot",
        "presale",
        "whitelist",
        "fomo",
        "hurry",
        "limited offer",
        "first come",
        "$FRIEND",
        "socialfi",
        "meme coin",
        "nft giveaway",
        "អាកាសយាន",
        "ថេរូវ",
        "គ្រាប់បរិច្ចាគ",
        "ឥតគិតថ្លៃ",
    ]

    # Check for URL patterns
    url_pattern = re.compile(r"https?://\S+|www\.\S+")
    has_url = bool(url_pattern.search(text.lower()))

    text_lower = text.lower()
    return any(keyword in text_lower for keyword in prohibited_keywords) or has_url


async def is_prohibited_image(image_file: BytesIO) -> bool:
    """Check if image contains gambling/crypto scam characteristics"""
    try:
        with Image.open(image_file) as img:
            # Convert to numpy array for analysis
            img_array = np.array(img)

            # Example checks (customize these thresholds based on your needs):
            # 1. Check if image is mostly red (common in gambling/casino ads)
            red_dominant = np.mean(img_array[:, :, 0]) > 180  # High red channel

            # 2. Check for bright/neon colors (common in scam ads)
            brightness = np.mean(img_array) > 200  # High brightness

            # 3. Check if image contains QR codes (common in crypto scams)
            # (Would need additional QR detection library)

            return red_dominant or brightness

    except Exception as e:
        print(f"Image analysis error: {e}")
        return False


async def all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all users registered in the bot"""
    if update.effective_user.id not in admins:
        await update.message.reply_text("❌ You are not authorized!")
        return

    if not customer_registry:
        await update.message.reply_text("No users registered yet.")
        return

    user_list = "\n".join(
        f"🛂 {qn} - {data.get('customer_name', 'Unknown')} - {data.get('plate', 'No plate')}"
        for qn, data in customer_registry.items()
    )

    await update.message.reply_text(f"Registered Users:\n{user_list}")


async def filter_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Filter out prohibited content in text, images, and documents"""
    if not update.message:
        return

    # Check text messages
    if update.message.text and is_prohibited_message(update.message.text):
        await handle_prohibited_content(update, context, "text")
        return

    # Check image captions
    if update.message.caption and is_prohibited_message(update.message.caption):
        await handle_prohibited_content(update, context, "image caption")
        return

    # Check images (photos)
    if update.message.photo:
        try:
            # Get the highest resolution photo
            photo_file = await update.message.photo[-1].get_file()
            image_data = BytesIO()
            await photo_file.download_to_memory(image_data)

            if await is_prohibited_image(image_data):
                await handle_prohibited_content(update, context, "image content")
                return

        except Exception as e:
            print(f"Image processing error: {e}")


async def handle_prohibited_content(
    update: Update, context: ContextTypes.DEFAULT_TYPE, content_type: str
):
    """Handle the deletion and warning for prohibited content"""
    user = update.effective_user
    warning_msg = (
        "⚠️ *WARNING* ⚠️\n\n"
        f"Prohibited {content_type} detected!\n"
        "This bot does not allow:\n"
        "- Games/Gambling content\n"
        "- Crypto Scams\n"
        "- Suspicious images\n\n"
        "ការប្រកាសមាតិកាដែលមិនត្រូវបានអនុញ្ញាត៖\n"
        "- ល្បែង/ភ្នាល់\n"
        "- ការបោកប្រាស់គ្រីបតូ\n"
        "- រូបភាពសង្ស័យ"
    )

    try:
        # Only try to delete if in a group/supergroup and bot has permission
        chat = update.effective_chat
        bot_user = await context.bot.get_me()
        chat_member = await context.bot.get_chat_member(chat.id, bot_user.id)
        can_delete = (
            chat.type in ["group", "supergroup"]
            and hasattr(chat_member, "can_delete_messages")
            and getattr(chat_member, "can_delete_messages", False)
        )
        if can_delete:
            await update.message.delete()
            deleted = True
        else:
            print(
                "Bot cannot delete messages in this chat (insufficient permissions, not a group, or attribute missing)."
            )
            deleted = False
    except Exception as e:
        # Telegram may raise "Message can't be deleted for everyone"
        print(f"Couldn't delete prohibited message: {e}")
        deleted = False

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=warning_msg,
        parse_mode="Markdown",
    )

    # Log the violation
    print(
        f"Blocked prohibited {content_type} from {user.id} ({user.username}) (deleted: {deleted})"
    )


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
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, filter_messages))
    app.add_handler(
        MessageHandler(
            (filters.CAPTION | filters.TEXT) & ~filters.COMMAND, filter_messages
        )
    )

    app.add_handler(CommandHandler("ready", ready))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("status", check_status))
    app.add_handler(CommandHandler("listadmins", list_admins))
    app.add_handler(CommandHandler("cancel", cancel))

    # Webhook setup for Render

    app.run_polling()


if __name__ == "__main__":
    main()
