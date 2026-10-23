import json
import os
import asyncio
import logging
import time
import re
import html
from datetime import datetime, timedelta
from urllib.parse import quote

import aiohttp
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatMember,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.error import BadRequest, TelegramError

# ---------------------------------------------------------------------------
# HARDCODED CONFIGURATION
# ---------------------------------------------------------------------------
BOT_TOKEN = "8674712607:AAFWafgghfguqqP52jBVBg_7FrLXakkS694"
OWNER_ID = 8505983842
DEV_USERNAME = "@ap_ultimate07"
DB_FILE = "database.json"

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------------------------
def default_db():
    return {
        "users": {},
        "redeem_codes": {},
        "force_sub_channels": [],
        "api_urls": {
            "number": "https://free.proapis.bond/num?number={text}",
            "gemini": "https://api-rebix.zone.id/api/gemini?q={text}",
            "girlfriend": "https://tuhari-girlfriend.vercel.app/gf?prompt={text}",
            "snapchat": "https://api-rebix.zone.id/api/snapchat?username={text}",
            "voice": "https://ai-pom-pom-bala.onrender.com/voice?text={text}&lang=hi&speed=0.85",
            "image": "https://image.pollinations.ai/prompt/{text}",
            "osint": "https://free.proapis.bond/leak?query={text}",
            "claude": "https://api-rebix.zone.id/api/claude-session?q={text}",
        },
        "features_enabled": {
            "number": True,
            "gemini": True,
            "girlfriend": True,
            "snapchat": True,
            "voice": True,
            "image": True,
            "osint": True,
            "claude": True,
        },
        "premium_price": 99,
    }


def load_db():
    if not os.path.exists(DB_FILE):
        db = default_db()
        save_db(db)
        return db
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        db = default_db()
        save_db(db)
        return db


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def get_user(db, user_id):
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "credits": 10,
            "premium_until": 0,
            "referred_by": None,
            "referral_count": 0,
            "total_searches": 0,
        }
        save_db(db)
    return db["users"][uid]


def is_premium(user):
    return user.get("premium_until", 0) > time.time()


# ---------------------------------------------------------------------------
# UI KEYBOARDS
# ---------------------------------------------------------------------------
def main_menu_keyboard(is_owner=False):
    keyboard = [
        [
            InlineKeyboardButton("🔍 Search Menu", callback_data="search_menu"),
            InlineKeyboardButton("👤 My Profile", callback_data="profile"),
        ],
        [
            InlineKeyboardButton("🎁 Refer & Earn", callback_data="refer"),
            InlineKeyboardButton("💎 Premium", callback_data="premium"),
        ],
        [
            InlineKeyboardButton("🎉 Redeem Code", callback_data="redeem"),
            InlineKeyboardButton("📞 Support", callback_data="support"),
        ],
    ]
    if is_owner:
        keyboard.append(
            [InlineKeyboardButton("🛡️ Admin Panel", callback_data="admin_panel")]
        )
    return InlineKeyboardMarkup(keyboard)


def search_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📱 Number to Information", callback_data="feat_number"),
            InlineKeyboardButton("🤖 AI Chat (Gemini)", callback_data="feat_gemini"),
        ],
        [
            InlineKeyboardButton("💕 Girlfriend Chat", callback_data="feat_girlfriend"),
            InlineKeyboardButton("👻 Snapchat Lookup", callback_data="feat_snapchat"),
        ],
        [
            InlineKeyboardButton("🎤 Text to Voice", callback_data="feat_voice"),
            InlineKeyboardButton("🖼️ Text to Image", callback_data="feat_image"),
        ],
        [
            InlineKeyboardButton("🕵️ OSINT Lookup", callback_data="feat_osint"),
            InlineKeyboardButton("☁️ Claude AI", callback_data="feat_claude"),
        ],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_panel_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Credits", callback_data="admin_add_credits"),
            InlineKeyboardButton("➖ Remove Credits", callback_data="admin_remove_credits"),
        ],
        [
            InlineKeyboardButton("⭐ Give Premium", callback_data="admin_give_premium"),
            InlineKeyboardButton("🗑️ Remove Premium", callback_data="admin_remove_premium"),
        ],
        [
            InlineKeyboardButton("🎟️ Create Redeem Code", callback_data="admin_create_code"),
            InlineKeyboardButton("❌ Delete Redeem Code", callback_data="admin_delete_code"),
        ],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [
            InlineKeyboardButton("🔗 Add Force Sub", callback_data="admin_add_fsub"),
            InlineKeyboardButton("🔓 Remove Force Sub", callback_data="admin_remove_fsub"),
        ],
        [InlineKeyboardButton("⚙️ API Manager", callback_data="admin_api_manager")],
        [InlineKeyboardButton("🔛 Feature Toggle", callback_data="admin_feature_toggle")],
        [InlineKeyboardButton("💰 Set Premium Price", callback_data="admin_set_premium_price")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def api_manager_keyboard(api_urls):
    keyboard = []
    for key, url in api_urls.items():
        label = f"{key.capitalize()} API"
        keyboard.append(
            [InlineKeyboardButton(label, callback_data=f"admin_edit_api:{key}")]
        )
    keyboard.append(
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")]
    )
    return InlineKeyboardMarkup(keyboard)


def feature_toggle_keyboard(features):
    keyboard = []
    for key, enabled in features.items():
        status = "✅ ON" if enabled else "❌ OFF"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{key.capitalize()} [{status}]",
                    callback_data=f"admin_toggle_feature:{key}",
                )
            ]
        )
    keyboard.append(
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")]
    )
    return InlineKeyboardMarkup(keyboard)


def force_sub_keyboard(channels):
    keyboard = []
    for ch in channels:
        if ch.startswith("@"):
            url = f"https://t.me/{ch[1:]}"
        elif ch.startswith("-100"):
            url = f"https://t.me/c/{ch[4:]}"
        else:
            url = f"https://t.me/{ch}"
        keyboard.append([InlineKeyboardButton(f"📢 Join {ch}", url=url)])
    keyboard.append(
        [InlineKeyboardButton("🔄 Try Again", callback_data="check_force_sub")]
    )
    return InlineKeyboardMarkup(keyboard)


def cancel_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_awaiting")]]
    )


# ---------------------------------------------------------------------------
# SAFE EDIT
# ---------------------------------------------------------------------------
async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        logger.warning(f"BadRequest in safe_edit: {e}")
    except TelegramError as e:
        logger.error(f"TelegramError in safe_edit: {e}")


# ---------------------------------------------------------------------------
# FORCE SUBSCRIBE CHECK
# ---------------------------------------------------------------------------
async def check_force_subscription(bot, user_id, db):
    channels = db.get("force_sub_channels", [])
    if not channels:
        return True, []
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in [
                ChatMember.MEMBER,
                ChatMember.ADMINISTRATOR,
                ChatMember.OWNER,
            ]:
                continue
            missing.append(ch)
        except Exception:
            missing.append(ch)
    return len(missing) == 0, missing


# ---------------------------------------------------------------------------
# API REQUEST HELPERS
# ---------------------------------------------------------------------------
async def fetch_json(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
            if resp.status != 200:
                return None, f"API error: HTTP {resp.status}"
            data = await resp.json()
            return data, None
    except asyncio.TimeoutError:
        return None, "Request timed out. Please try again."
    except Exception as e:
        return None, f"Request failed: {str(e)}"


def extract_text_from_json(data):
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in [
            "response",
            "result",
            "text",
            "answer",
            "message",
            "reply",
            "output",
            "content",
            "data",
        ]:
            if key in data and isinstance(data[key], str):
                return data[key]
        return json.dumps(data, indent=2, ensure_ascii=False)
    return str(data)


def format_number_response(data, dev_username):
    # Deep copy to avoid mutating original
    import copy

    obj = copy.deepcopy(data)
    # Remove developer/creator fields
    remove_keys = {"developer", "creator", "author", "made_by", "dev", "credit"}
    # Replace nulls and rename id
    def process(item):
        if isinstance(item, dict):
            for k in list(item.keys()):
                if k.lower() in remove_keys:
                    del item[k]
                else:
                    process(item[k])
            if "id" in item:
                item["Aadhar Card"] = item.pop("id")
            for k, v in item.items():
                if v is None:
                    item[k] = "Not Available"
        elif isinstance(item, list):
            for i in item:
                process(i)

    process(obj)
    # Hardcode developer
    if isinstance(obj, dict):
        obj["Developer"] = dev_username
        # Remove any leftover creator keys
        for k in list(obj.keys()):
            if k.lower() in remove_keys:
                del obj[k]
    return obj


def pretty_json(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# POST INIT / SHUTDOWN
# ---------------------------------------------------------------------------
async def post_init(application: Application):
    application.bot_data["session"] = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=45)
    )
    logger.info("aiohttp session created.")


async def post_shutdown(application: Application):
    session = application.bot_data.get("session")
    if session:
        await session.close()
    logger.info("aiohttp session closed.")


# ---------------------------------------------------------------------------
# /start COMMAND
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = load_db()
    get_user(db, user.id)

    # Handle referral
    if context.args:
        ref_id = context.args[0]
        if ref_id != str(user.id) and ref_id in db["users"]:
            referrer = db["users"][ref_id]
            referrer["credits"] += 5
            referrer["referral_count"] = referrer.get("referral_count", 0) + 1
            db["users"][str(user.id)]["referred_by"] = ref_id
            save_db(db)
            try:
                await context.bot.send_message(
                    chat_id=int(ref_id),
                    text=f"🎉 You earned 5 credits from a referral!",
                )
            except Exception:
                pass

    text = (
        f"👋 Welcome <b>{html.escape(user.first_name)}</b>!\n\n"
        f"💎 <b>Ultra Premium Bot</b>\n"
        f"Your all-in-one OSINT & AI toolkit.\n\n"
        f"Choose an option below:"
    )
    await update.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(user.id == OWNER_ID),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# MAIN BUTTON HANDLER (Routes all callback queries)
# ---------------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = update.effective_user
    user_id = user.id
    is_owner = user_id == OWNER_ID
    db = load_db()
    user_data = get_user(db, user_id)

    # Handle Cancel awaiting
    if data == "cancel_awaiting":
        context.user_data.pop("awaiting", None)
        await safe_edit(
            query,
            "❌ Action cancelled.",
            reply_markup=main_menu_keyboard(is_owner),
        )
        return

    # Handle Try Again for force sub
    if data == "check_force_sub":
        ok, missing = await check_force_subscription(context.bot, user_id, db)
        if ok:
            await safe_edit(
                query,
                "✅ You are subscribed! Use the menu below.",
                reply_markup=main_menu_keyboard(is_owner),
            )
        else:
            await safe_edit(
                query,
                "⚠️ You must join all required channels first.",
                reply_markup=force_sub_keyboard(missing),
            )
        return

    # Force subscribe guard for feature actions
    if data.startswith("feat_") or data in ["search_menu", "profile", "refer", "premium", "redeem"]:
        ok, missing = await check_force_subscription(context.bot, user_id, db)
        if not ok:
            await safe_edit(
                query,
                "🔒 Please join our channels to use the bot.",
                reply_markup=force_sub_keyboard(missing),
            )
            return

    # -----------------------------------------------------------------------
    # MAIN MENU ROUTES
    # -----------------------------------------------------------------------
    if data == "main_menu":
        context.user_data.pop("awaiting", None)
        await safe_edit(
            query,
            "🏠 <b>Main Menu</b>\nChoose an option:",
            reply_markup=main_menu_keyboard(is_owner),
            parse_mode="HTML",
        )
        return

    if data == "search_menu":
        context.user_data.pop("awaiting", None)
        await safe_edit(
            query,
            "🔍 <b>Search Menu</b>\nSelect a feature below. Each search costs 1 credit (Premium = unlimited).",
            reply_markup=search_menu_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "profile":
        premium_status = "✅ Active" if is_premium(user_data) else "❌ Inactive"
        if is_premium(user_data):
            expiry = datetime.fromtimestamp(user_data["premium_until"]).strftime(
                "%d %b %Y"
            )
            premium_status += f" (until {expiry})"
        text = (
            f"👤 <b>Your Profile</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"💰 Credits: <b>{user_data['credits']}</b>\n"
            f"💎 Premium: {premium_status}\n"
            f"👥 Referrals: {user_data.get('referral_count', 0)}\n"
            f"🔍 Total Searches: {user_data.get('total_searches', 0)}"
        )
        await safe_edit(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
            ),
            parse_mode="HTML",
        )
        return

    if data == "refer":
        bot_username = context.bot.username or "YourBot"
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        text = (
            f"🎁 <b>Refer & Earn</b>\n\n"
            f"Share your referral link and earn <b>5 credits</b> for each new user.\n\n"
            f"🔗 Your link:\n<code>{ref_link}</code>\n\n"
            f"👥 Total referrals: {user_data.get('referral_count', 0)}"
        )
        await safe_edit(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
            ),
            parse_mode="HTML",
        )
        return

    if data == "premium":
        price = db.get("premium_price", 99)
        text = (
            f"💎 <b>Premium Membership</b>\n\n"
            f"• Unlimited searches\n"
            f"• Priority processing\n"
            f"• No credit deductions\n\n"
            f"💰 Price: <b>₹{price}</b> / month\n\n"
            f"To purchase, contact {DEV_USERNAME}."
        )
        await safe_edit(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
            ),
            parse_mode="HTML",
        )
        return

    if data == "redeem":
        context.user_data["awaiting"] = "redeem_code"
        await safe_edit(
            query,
            "🎉 Please send your redeem code.\nExample: <code>PREMIUM2024</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "support":
        await safe_edit(
            query,
            f"📞 <b>Support</b>\n\nContact: {DEV_USERNAME}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
            ),
            parse_mode="HTML",
        )
        return

    # -----------------------------------------------------------------------
    # ADMIN PANEL
    # -----------------------------------------------------------------------
    if data == "admin_panel":
        if not is_owner:
            await query.answer("⛔ Unauthorized.", show_alert=True)
            return
        await safe_edit(
            query,
            "🛡️ <b>Admin Panel</b>\nSelect an action:",
            reply_markup=admin_panel_keyboard(),
            parse_mode="HTML",
        )
        return

    if data.startswith("admin_") and not is_owner:
        await query.answer("⛔ Unauthorized.", show_alert=True)
        return

    # Admin actions
    if data == "admin_add_credits":
        context.user_data["awaiting"] = "admin_add_credits"
        await safe_edit(
            query,
            "➕ Send: <code>USER_ID AMOUNT</code>\nExample: <code>8505983842 50</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    if data == "admin_remove_credits":
        context.user_data["awaiting"] = "admin_remove_credits"
        await safe_edit(
            query,
            "➖ Send: <code>USER_ID AMOUNT</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    if data == "admin_give_premium":
        context.user_data["awaiting"] = "admin_give_premium"
        await safe_edit(
            query,
            "⭐ Send: <code>USER_ID DAYS</code>\nExample: <code>8505983842 30</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    if data == "admin_remove_premium":
        context.user_data["awaiting"] = "admin_remove_premium"
        await safe_edit(
            query,
            "🗑️ Send: <code>USER_ID</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    if data == "admin_create_code":
        context.user_data["awaiting"] = "admin_create_code"
        await safe_edit(
            query,
            "🎟️ Send: <code>CODE CREDITS LIMIT</code>\nExample: <code>WELCOME100 100 10</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    if data == "admin_delete_code":
        context.user_data["awaiting"] = "admin_delete_code"
        await safe_edit(
            query,
            "❌ Send: <code>CODE</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    if data == "admin_broadcast":
        context.user_data["awaiting"] = "admin_broadcast"
        await safe_edit(
            query,
            "📢 Send the broadcast message (text only).",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    if data == "admin_add_fsub":
        context.user_data["awaiting"] = "admin_add_fsub"
        await safe_edit(
            query,
            "🔗 Send channel ID or @username.\nExample: <code>@mychannel</code> or <code>-1001234567890</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    if data == "admin_remove_fsub":
        context.user_data["awaiting"] = "admin_remove_fsub"
        await safe_edit(
            query,
            "🔓 Send channel ID or @username to remove.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_api_manager":
        await safe_edit(
            query,
            "⚙️ <b>API Manager</b>\nSelect an API to change its URL:",
            reply_markup=api_manager_keyboard(db["api_urls"]),
            parse_mode="HTML",
        )
        return
    if data.startswith("admin_edit_api:"):
        api_key = data.split(":", 1)[1]
        context.user_data["awaiting"] = f"admin_edit_api:{api_key}"
        current = db["api_urls"].get(api_key, "")
        await safe_edit(
            query,
            f"✏️ Send the new URL for <b>{api_key}</b>.\n\nCurrent:\n<code>{html.escape(current)}</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    if data == "admin_feature_toggle":
        await safe_edit(
            query,
            "🔛 <b>Feature Toggle</b>\nClick to toggle:",
            reply_markup=feature_toggle_keyboard(db["features_enabled"]),
            parse_mode="HTML",
        )
        return
    if data.startswith("admin_toggle_feature:"):
        feat = data.split(":", 1)[1]
        if feat in db["features_enabled"]:
            db["features_enabled"][feat] = not db["features_enabled"][feat]
            save_db(db)
        await safe_edit(
            query,
            "🔛 <b>Feature Toggle</b>\nClick to toggle:",
            reply_markup=feature_toggle_keyboard(db["features_enabled"]),
            parse_mode="HTML",
        )
        return

    if data == "admin_set_premium_price":
        context.user_data["awaiting"] = "admin_set_premium_price"
        await safe_edit(
            query,
            "💰 Send the new premium price (number).\nExample: <code>149</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    # -----------------------------------------------------------------------
    # FEATURE PROMPTS (when user clicks a feature button)
    # -----------------------------------------------------------------------
    if data.startswith("feat_"):
        feature = data[5:]  # strip "feat_"
        if not db["features_enabled"].get(feature, True):
            await safe_edit(
                query,
                "⚠️ This feature is currently disabled by the admin.",
                reply_markup=search_menu_keyboard(),
            )
            return

        examples = {
            "number": "Please send a 10-digit mobile number.\nExample: <code>9876543210</code>",
            "gemini": "Ask Gemini anything.\nExample: <code>What is the capital of India?</code>",
            "girlfriend": "Chat with your AI girlfriend.\nExample: <code>I had a long day, cheer me up!</code>",
            "snapchat": "Enter a Snapchat username.\nExample: <code>john_doe</code>",
            "voice": "Send text to convert to voice.\nExample: <code>Hello, how are you?</code>",
            "image": "Describe the image you want.\nExample: <code>a cyberpunk city at night, neon lights</code>",
            "osint": "Enter a query for OSINT lookup.\nExample: <code>9876543210</code>",
            "claude": "Ask Claude AI anything.\nExample: <code>Write a short poem about the moon.</code>",
        }
        context.user_data["awaiting"] = f"feat_{feature}"
        await safe_edit(
            query,
            examples.get(feature, "Please send your input."),
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return


# ---------------------------------------------------------------------------
# TEXT INPUT HANDLER (State management)
# ---------------------------------------------------------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    awaiting = context.user_data.get("awaiting")
    if not awaiting:
        return

    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id
    is_owner = user_id == OWNER_ID
    db = load_db()
    user_data = get_user(db, user_id)

    # Clear awaiting for command-like inputs
    if text.startswith("/"):
        context.user_data.pop("awaiting", None)
        return

    # -----------------------------------------------------------------------
    # USER FEATURES
    # -----------------------------------------------------------------------
    if awaiting.startswith("feat_"):
        feature = awaiting[5:]

        if not db["features_enabled"].get(feature, True):
            await update.message.reply_text("⚠️ This feature is disabled.")
            context.user_data.pop("awaiting", None)
            return

        # Check credits
        if not is_premium(user_data) and user_data["credits"] < 1:
            await update.message.reply_text(
                "❌ Insufficient credits. Please refer friends or upgrade to Premium.",
                reply_markup=main_menu_keyboard(is_owner),
            )
            context.user_data.pop("awaiting", None)
            return

        # Process based on feature
        session = context.bot_data["session"]
        api_urls = db["api_urls"]

        # ----- NUMBER -----
        if feature == "number":
            if not re.match(r"^\d{10}$", text):
                await update.message.reply_text(
                    "❌ Invalid number. Please send a 10-digit mobile number.\nExample: 9876543210"
                )
                return
            url = api_urls["number"].format(text=quote(text))
            data, err = await fetch_json(session, url)
            if err:
                await update.message.reply_text(f"❌ {err}")
                return
            formatted = format_number_response(data, DEV_USERNAME)
            result_text = pretty_json(formatted)
            # Deduct credit only after success
            if not is_premium(user_data):
                user_data["credits"] -= 1
            user_data["total_searches"] = user_data.get("total_searches", 0) + 1
            save_db(db)
            await update.message.reply_text(
                f"📱 <b>Number Information</b>\n\n<pre>{html.escape(result_text)}</pre>",
                parse_mode="HTML",
            )

        # ----- GEMINI -----
        elif feature == "gemini":
            url = api_urls["gemini"].format(text=quote(text))
            data, err = await fetch_json(session, url)
            if err:
                await update.message.reply_text(f"❌ {err}")
                return
            result = extract_text_from_json(data)
            if not is_premium(user_data):
                user_data["credits"] -= 1
            user_data["total_searches"] += 1
            save_db(db)
            await update.message.reply_text(
                f"🤖 <b>Gemini AI</b>\n\n{html.escape(result)}",
                parse_mode="HTML",
            )

        # ----- GIRLFRIEND -----
        elif feature == "girlfriend":
            url = api_urls["girlfriend"].format(text=quote(text))
            data, err = await fetch_json(session, url)
            if err:
                await update.message.reply_text(f"❌ {err}")
                return
            result = extract_text_from_json(data)
            if not is_premium(user_data):
                user_data["credits"] -= 1
            user_data["total_searches"] += 1
            save_db(db)
            await update.message.reply_text(
                f"💕 <b>Girlfriend Chat</b>\n\n{html.escape(result)}",
                parse_mode="HTML",
            )

        # ----- SNAPCHAT -----
        elif feature == "snapchat":
            url = api_urls["snapchat"].format(text=quote(text))
            data, err = await fetch_json(session, url)
            if err:
                await update.message.reply_text(f"❌ {err}")
                return
            result = pretty_json(data) if isinstance(data, (dict, list)) else str(data)
            if not is_premium(user_data):
                user_data["credits"] -= 1
            user_data["total_searches"] += 1
            save_db(db)
            await update.message.reply_text(
                f"👻 <b>Snapchat Lookup</b>\n\n<pre>{html.escape(result)}</pre>",
                parse_mode="HTML",
            )

        # ----- VOICE -----
        elif feature == "voice":
            url = api_urls["voice"].format(text=quote(text))
            try:
                if not is_premium(user_data):
                    user_data["credits"] -= 1
                user_data["total_searches"] += 1
                save_db(db)
                await update.message.reply_voice(voice=url)
            except Exception as e:
                # Refund credit on failure
                if not is_premium(user_data):
                    user_data["credits"] += 1
                user_data["total_searches"] -= 1
                save_db(db)
                await update.message.reply_text(f"❌ Voice generation failed: {e}")

        # ----- IMAGE -----
        elif feature == "image":
            url = api_urls["image"].format(text=quote(text))
            try:
                if not is_premium(user_data):
                    user_data["credits"] -= 1
                user_data["total_searches"] += 1
                save_db(db)
                await update.message.reply_photo(photo=url)
            except Exception as e:
                if not is_premium(user_data):
                    user_data["credits"] += 1
                user_data["total_searches"] -= 1
                save_db(db)
                await update.message.reply_text(f"❌ Image generation failed: {e}")

        # ----- OSINT -----
        elif feature == "osint":
            url = api_urls["osint"].format(text=quote(text))
            data, err = await fetch_json(session, url)
            if err:
                await update.message.reply_text(f"❌ {err}")
                return
            result = pretty_json(data)
            if not is_premium(user_data):
                user_data["credits"] -= 1
            user_data["total_searches"] += 1
            save_db(db)
            await update.message.reply_text(
                f"🕵️ <b>OSINT Lookup</b>\n\n<pre>{html.escape(result)}</pre>",
                parse_mode="HTML",
            )

        # ----- CLAUDE -----
        elif feature == "claude":
            url = api_urls["claude"].format(text=quote(text))
            data, err = await fetch_json(session, url)
            if err:
                await update.message.reply_text(f"❌ {err}")
                return
            result = extract_text_from_json(data)
            if not is_premium(user_data):
                user_data["credits"] -= 1
            user_data["total_searches"] += 1
            save_db(db)
            await update.message.reply_text(
                f"☁️ <b>Claude AI</b>\n\n{html.escape(result)}",
                parse_mode="HTML",
            )

        context.user_data.pop("awaiting", None)
        await update.message.reply_text(
            "✅ Done! Use the menu to continue.",
            reply_markup=main_menu_keyboard(is_owner),
        )
        return

    # -----------------------------------------------------------------------
    # REDEEM CODE
    # -----------------------------------------------------------------------
    if awaiting == "redeem_code":
        code = text.upper()
        if code not in db["redeem_codes"]:
            await update.message.reply_text("❌ Invalid redeem code.")
            context.user_data.pop("awaiting", None)
            return
        rc = db["redeem_codes"][code]
        if rc.get("used", 0) >= rc.get("limit", 1):
            await update.message.reply_text("❌ This code has reached its limit.")
            context.user_data.pop("awaiting", None)
            return
        user_data["credits"] += rc["credits"]
        rc["used"] = rc.get("used", 0) + 1
        save_db(db)
        context.user_data.pop("awaiting", None)
        await update.message.reply_text(
            f"🎉 Code redeemed! You received <b>{rc['credits']}</b> credits.",
            reply_markup=main_menu_keyboard(is_owner),
            parse_mode="HTML",
        )
        return

    # -----------------------------------------------------------------------
    # ADMIN INPUTS
    # -----------------------------------------------------------------------
    if awaiting.startswith("admin_") and is_owner:
        try:
            if awaiting == "admin_add_credits":
                parts = text.split()
                if len(parts) != 2:
                    raise ValueError("Invalid format.")
                target_id, amount = parts
                amount = int(amount)
                target = get_user(db, target_id)
                target["credits"] += amount
                save_db(db)
                await update.message.reply_text(
                    f"✅ Added {amount} credits to {target_id}."
                )

            elif awaiting == "admin_remove_credits":
                parts = text.split()
                if len(parts) != 2:
                    raise ValueError("Invalid format.")
                target_id, amount = parts
                amount = int(amount)
                target = get_user(db, target_id)
                target["credits"] = max(0, target["credits"] - amount)
                save_db(db)
                await update.message.reply_text(
                    f"✅ Removed {amount} credits from {target_id}."
                )

            elif awaiting == "admin_give_premium":
                parts = text.split()
                if len(parts) != 2:
                    raise ValueError("Invalid format.")
                target_id, days = parts
                days = int(days)
                target = get_user(db, target_id)
                current = max(target["premium_until"], time.time())
                target["premium_until"] = current + days * 86400
                save_db(db)
                await update.message.reply_text(
                    f"✅ Gave {days} days premium to {target_id}."
                )

            elif awaiting == "admin_remove_premium":
                target_id = text.strip()
                target = get_user(db, target_id)
                target["premium_until"] = 0
                save_db(db)
                await update.message.reply_text(
                    f"✅ Removed premium from {target_id}."
                )

            elif awaiting == "admin_create_code":
                parts = text.split()
                if len(parts) != 3:
                    raise ValueError("Invalid format.")
                code, credits, limit = parts
                code = code.upper()
                db["redeem_codes"][code] = {
                    "credits": int(credits),
                    "limit": int(limit),
                    "used": 0,
                }
                save_db(db)
                await update.message.reply_text(
                    f"✅ Created code <code>{code}</code> with {credits} credits, limit {limit}.",
                    parse_mode="HTML",
                )

            elif awaiting == "admin_delete_code":
                code = text.upper()
                if code in db["redeem_codes"]:
                    del db["redeem_codes"][code]
                    save_db(db)
                    await update.message.reply_text(f"✅ Deleted code {code}.")
                else:
                    await update.message.reply_text("❌ Code not found.")

            elif awaiting == "admin_broadcast":
                sent = 0
                failed = 0
                for uid in db["users"]:
                    try:
                        await context.bot.send_message(
                            chat_id=int(uid), text=text
                        )
                        sent += 1
                        await asyncio.sleep(0.05)  # rate limit
                    except Exception:
                        failed += 1
                await update.message.reply_text(
                    f"📢 Broadcast complete. Sent: {sent}, Failed: {failed}."
                )

            elif awaiting == "admin_add_fsub":
                ch = text.strip()
                if ch not in db["force_sub_channels"]:
                    db["force_sub_channels"].append(ch)
                    save_db(db)
                    await update.message.reply_text(f"✅ Added {ch} to force subscribe.")
                else:
                    await update.message.reply_text("⚠️ Already in list.")

            elif awaiting == "admin_remove_fsub":
                ch = text.strip()
                if ch in db["force_sub_channels"]:
                    db["force_sub_channels"].remove(ch)
                    save_db(db)
                    await update.message.reply_text(f"✅ Removed {ch}.")
                else:
                    await update.message.reply_text("⚠️ Not in list.")

            elif awaiting.startswith("admin_edit_api:"):
                api_key = awaiting.split(":", 1)[1]
                new_url = text.strip()
                if "{text}" not in new_url:
                    await update.message.reply_text(
                        "❌ URL must contain `{text}` placeholder."
                    )
                    return
                db["api_urls"][api_key] = new_url
                save_db(db)
                await update.message.reply_text(
                    f"✅ Updated {api_key} API URL.\n<code>{html.escape(new_url)}</code>",
                    parse_mode="HTML",
                )

            elif awaiting == "admin_set_premium_price":
                price = int(text.strip())
                db["premium_price"] = price
                save_db(db)
                await update.message.reply_text(
                    f"✅ Premium price set to ₹{price}."
                )

        except ValueError as e:
            await update.message.reply_text(f"❌ Invalid input: {e}")
            return
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
            return

        context.user_data.pop("awaiting", None)
        await update.message.reply_text(
            "✅ Done. Returning to Admin Panel.",
            reply_markup=admin_panel_keyboard(),
        )
        return


# ---------------------------------------------------------------------------
# ERROR HANDLER
# ---------------------------------------------------------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ An unexpected error occurred. Please try again.",
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Commands
    application.add_handler(CommandHandler("start", start))

    # Callback queries (all buttons)
    application.add_handler(CallbackQueryHandler(button_handler))

    # Text messages (for stateful input)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    # Error handler
    application.add_error_handler(error_handler)

    logger.info("Bot started. Polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()