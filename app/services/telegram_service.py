import logging
from datetime import time
import asyncio
import html
from typing import Optional
from telegram import Bot, Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    PicklePersistence,
)
from app.core.config import settings
from app.db import repository, database

logger = logging.getLogger(__name__)

# Conversation states for /set
CHOOSE_SETTING, RECEIVE_VALUE = range(2)
# Conversation states for /chats
CHATS_MENU, GET_ADD_CHAT_ID, GET_REMOVE_CHAT_ID = range(2, 5)

class TelegramService:
    CHANGEABLE_SETTINGS = {
        "MAX_SIGNALS_PER_DAY": int,
        "MIN_SECONDS_BETWEEN_SIGNALS": int,
        "TRADING_START_TIME": str,
        "TRADING_END_TIME": str,
    }

    def __init__(self):
        self.bot: Optional[Bot] = None
        self.app: Optional[Application] = None

    async def initialize(self):
        """Initialize the bot, set commands, and set up handlers."""
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.warning("TELEGRAM_BOT_TOKEN is not set. Telegram service will be disabled.")
            return

        # Setup persistence
        persistence = PicklePersistence(filepath="./telegram_persistence.pkl")

        self.app = (
            Application.builder()
            .token(settings.TELEGRAM_BOT_TOKEN)
            .persistence(persistence)
            .build()
        )
        self.bot = self.app.bot

        # Ensure default chat is in the database
        try:
            chat = await self.bot.get_chat(settings.TELEGRAM_DEFAULT_CHAT_ID)
            conn = database.create_bot_connection()
            repository.add_chat(conn, str(chat.id), chat.title or f"Chat {chat.id}")
            conn.close()
            logger.info(f"Ensured default chat '{chat.title}' ({chat.id}) is in the database.")
        except Exception as e:
            logger.error(f"Could not get default chat info. Please ensure the bot is a member of the chat with ID {settings.TELEGRAM_DEFAULT_CHAT_ID}. Error: {e}")

        # Set the bot's command menu
        commands = [
            BotCommand("stats", "View today's trading statistics"),
            BotCommand("pause", "Pause the bot from processing new signals"),
            BotCommand("resume", "Resume the bot and process new signals"),
            BotCommand("set", "Change a bot setting via an interactive menu"),
            BotCommand("chats", "Manage channels/groups receiving signals"),
            BotCommand("help", "Show help message and available commands"),
            BotCommand("cancel", "Cancel the current operation"),
        ]
        await self.bot.set_my_commands(commands)
        logger.info("Bot command menu has been set.")

        # Conversation handler for /set
        set_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("set", self.cmd_set)],
            states={
                CHOOSE_SETTING: [CallbackQueryHandler(self.handle_setting_choice)],
                RECEIVE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_new_value)],
            },
            fallbacks=[CommandHandler("cancel", self.cmd_cancel)],
        )

        # Conversation handler for /chats
        chats_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("chats", self.cmd_chats)],
            states={
                CHATS_MENU: [CallbackQueryHandler(self.handle_chats_menu_choice)],
                GET_ADD_CHAT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_add_chat_id)],
                GET_REMOVE_CHAT_ID: [CallbackQueryHandler(self.handle_remove_chat_choice)],
            },
            fallbacks=[CommandHandler("cancel", self.cmd_cancel)],
        )

        # Add command handlers
        self.app.add_handler(set_conv_handler)
        self.app.add_handler(chats_conv_handler)
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("pause", self.cmd_pause))
        self.app.add_handler(CommandHandler("resume", self.cmd_resume))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("cancel", self.cmd_cancel))

        await self.app.initialize()
        await self.app.start()
        if self.app.updater:
            asyncio.create_task(self.app.updater.start_polling(drop_pending_updates=True))
        logger.info("Telegram bot initialized and polling started.")

    async def shutdown(self):
        if self.app:
            if self.app.updater and self.app.updater.running:
                await self.app.updater.stop()
            await self.app.stop()
            logger.info("Telegram bot has been shut down.")

    async def send_alert(self, message: str):
        """Send a message to all managed chats in the database."""
        if not self.bot:
            logger.error("Telegram bot is not initialized. Cannot send alert.")
            return
        
        conn = database.create_bot_connection()
        try:
            chats = repository.get_all_chats(conn)
            for chat in chats:
                try:
                    await self.bot.send_message(chat_id=chat["chat_id"], text=message, parse_mode='HTML')
                    logger.info(f"Telegram alert sent to chat: {chat['chat_name']} ({chat['chat_id']})")
                except Exception as e:
                    logger.error(f"Failed to send Telegram alert to {chat['chat_name']} ({chat['chat_id']}): {e}")
        finally:
            conn.close()

    def _is_admin(self, user_id: int) -> bool:
        return user_id in settings.ADMIN_USER_IDS

    # --- Conversation Handlers for /set ---
    
    async def cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Entry point for the /set conversation."""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔️ Unauthorized")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(name.replace("_", " ").title(), callback_data=name)]
            for name in self.CHANGEABLE_SETTINGS
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please choose a setting to change:", reply_markup=reply_markup)
        return CHOOSE_SETTING

    async def handle_setting_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle the user's choice of setting from the inline keyboard."""
        query = update.callback_query
        await query.answer()
        setting_name = query.data
        context.user_data['setting_to_change'] = setting_name

        current_value = getattr(settings, setting_name)
        
        prompt_text = f"Current value for <code>{setting_name}</code> is <code>{current_value or 'Not Set'}</code>.\n\n"
        
        # Add context-specific instructions to the prompt
        if setting_name == "MAX_SIGNALS_PER_DAY":
            prompt_text += "Please send the new value (e.g., 10) or send <b>unlimited</b>."
        elif "TIME" in setting_name:
            prompt_text += "Please send the new value in <b>HH:MM</b> format (24-hour UTC), or send <b>off</b> to disable."
        else:
            prompt_text += "Please send the new value."

        await query.edit_message_text(text=prompt_text, parse_mode='HTML')
        return RECEIVE_VALUE

    async def handle_new_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle the new value sent by the user, with validation."""
        setting_name = context.user_data.get('setting_to_change')
        if not setting_name:
            await update.message.reply_text("Something went wrong. Please start over with /set.")
            return ConversationHandler.END

        new_value_str = update.message.text.strip()
        value_type = self.CHANGEABLE_SETTINGS[setting_name]
        new_value = None
        error_msg = None

        try:
            if setting_name == "MAX_SIGNALS_PER_DAY":
                if new_value_str.lower() in ("unlimited", "0"):
                    new_value = 0
                else:
                    val = int(new_value_str)
                    if val < 0:
                        error_msg = "❌ Invalid value. Must be a positive number or 'unlimited'."
                    else:
                        new_value = val
            elif setting_name == "MIN_SECONDS_BETWEEN_SIGNALS":
                val = int(new_value_str)
                if val < 0:
                    error_msg = "❌ Invalid value. Must be a positive number."
                else:
                    new_value = val
            elif "TIME" in setting_name:
                if new_value_str.lower() == 'off':
                    new_value = None
                else:
                    # This will raise ValueError if format is wrong
                    parts = list(map(int, new_value_str.split(':')))
                    new_value = time(parts[0], parts[1])

        except (ValueError, IndexError):
            if "TIME" in setting_name:
                error_msg = "❌ Invalid format. Please use <b>HH:MM</b> (e.g., 09:30) or send <b>off</b>."
            else:
                error_msg = f"❌ Invalid value. Please enter a valid number."
        
        if error_msg:
            await update.message.reply_text(error_msg, parse_mode='HTML')
            return RECEIVE_VALUE # Stay in the same state to allow user to retry

        try:
            # Persist to DB
            conn = database.create_bot_connection()
            try:
                # Convert value to string for DB storage
                if new_value is None:
                    db_value = ""
                elif isinstance(new_value, time):
                    db_value = new_value.strftime('%H:%M')
                else:
                    db_value = str(new_value)
                
                repository.set_setting(conn, setting_name, db_value)
            finally:
                conn.close()

            # Update in-memory settings object
            old_value = getattr(settings, setting_name)
            setattr(settings, setting_name, new_value)
            
            # --- Format values for a user-friendly display message ---
            def format_for_display(key, value):
                if key == "MAX_SIGNALS_PER_DAY" and value == 0:
                    return "Unlimited"
                return value or "Not Set"

            old_value_display = format_for_display(setting_name, old_value)
            new_value_display = format_for_display(setting_name, new_value)
            # --- End of formatting ---

            logger.info(f"Admin {update.effective_user.id} changed setting {setting_name} from {old_value} to {new_value}")
            await update.message.reply_text(
                f"✅ Setting updated!\n<b>{setting_name}</b> changed from <code>{old_value_display}</code> to <code>{new_value_display}</code>.",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error updating setting {setting_name}: {e}")
            await update.message.reply_text("An unexpected error occurred.")
        
        context.user_data.clear()
        return ConversationHandler.END

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        # Check if a query exists and answer it to remove the "loading" icon
        if update.callback_query:
            await update.callback_query.answer()
        
        await update.effective_message.reply_text("Operation cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    # --- Conversation Handlers for /chats ---

    async def cmd_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Entry point for the /chats conversation."""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔️ Unauthorized")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton("List Current Chats", callback_data="list_chats")],
            [InlineKeyboardButton("Add a New Chat", callback_data="add_chat")],
            [InlineKeyboardButton("Remove a Chat", callback_data="remove_chat")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = "<b>Chat Management</b>\n\nSelect an action to manage the chat IDs that receive signals."
        
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
            
        return CHATS_MENU

    async def handle_chats_menu_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle user's choice from the main chats menu."""
        query = update.callback_query
        await query.answer()
        action = query.data

        conn = database.create_bot_connection()
        try:
            if action == "list_chats":
                chats = repository.get_all_chats(conn)
                
                # --- Auto-update chat names ---
                updated_chats = []
                for chat in chats:
                    try:
                        live_chat = await self.bot.get_chat(chat['chat_id'])
                        live_name = live_chat.title or f"Chat {live_chat.id}"
                        if live_name != chat['chat_name']:
                            repository.add_chat(conn, chat['chat_id'], live_name)
                            logger.info(f"Auto-updated chat name for {chat['chat_id']} from '{chat['chat_name']}' to '{live_name}'")
                        updated_chats.append({'chat_id': chat['chat_id'], 'chat_name': live_name})
                    except Exception as e:
                        logger.warning(f"Could not refresh name for chat {chat['chat_id']}: {e}. Using stored name.")
                        updated_chats.append(chat)
                # --- End auto-update ---

                if updated_chats:
                    text = "Signals are currently sent to:\n" + "\n".join(
                        f"• <b>{html.escape(c['chat_name'])}</b> (<code>{c['chat_id']}</code>)" for c in updated_chats
                    )
                else:
                    text = "No chat IDs are currently configured."
                
                keyboard = [[InlineKeyboardButton("« Back", callback_data="back_to_main")]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
                return CHATS_MENU

            elif action == "add_chat":
                await query.edit_message_text(
                    "Please send the new Chat ID.\n\n"
                    "<i>To get a channel/group ID, add this bot as an admin and forward a message from the chat to @userinfobot.</i>",
                    parse_mode='HTML'
                )
                return GET_ADD_CHAT_ID

            elif action == "remove_chat":
                chats = repository.get_all_chats(conn)
                if not chats:
                    keyboard = [[InlineKeyboardButton("« Back", callback_data="back_to_main")]]
                    await query.edit_message_text("There are no chat IDs to remove.", reply_markup=InlineKeyboardMarkup(keyboard))
                    return CHATS_MENU
                
                keyboard = [
                    [InlineKeyboardButton(f"Remove \"{chat['chat_name']}\"", callback_data=chat['chat_id'])] for chat in chats
                ]
                keyboard.append([InlineKeyboardButton("« Back", callback_data="back_to_main")])
                await query.edit_message_text("Select a chat to remove:", reply_markup=InlineKeyboardMarkup(keyboard))
                return GET_REMOVE_CHAT_ID
            
            elif action == "back_to_main":
                return await self.cmd_chats(update, context)

        finally:
            conn.close()
        
        return CHATS_MENU

    async def handle_add_chat_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Validate and add a new chat ID to the database."""
        chat_id_str = update.message.text.strip()
        
        try:
            # Basic validation for the ID format
            if not chat_id_str.startswith('-') or not chat_id_str[1:].isdigit():
                raise ValueError("Invalid chat ID format.")

            # Validate format and get chat info from Telegram API
            chat = await self.bot.get_chat(chat_id_str)
            chat_name = chat.title or f"Chat {chat.id}"

            conn = database.create_bot_connection()
            try:
                repository.add_chat(conn, str(chat.id), chat_name)
                await update.message.reply_text(f"✅ Successfully added chat: <b>{html.escape(chat_name)}</b> (<code>{chat.id}</code>)", parse_mode='HTML')
                logger.info(f"Admin {update.effective_user.id} added chat '{chat_name}' ({chat.id})")
            finally:
                conn.close()

        except ValueError:
            await update.message.reply_text(
                "❌ Invalid format. Chat IDs for channels and groups are negative numbers (e.g., -100123456789)."
            )
        except Exception as e: # Catches Telegram-related errors (e.g., bot not in chat)
            logger.warning(f"Failed to add chat ID {chat_id_str}. Error: {e}")
            await update.message.reply_text(
                "❌ Could not add chat.\nPlease ensure the ID is correct and that this bot is a member of the chat (with admin rights)."
            )
        
        # Go back to the main chats menu
        await self.cmd_chats(update, context)
        return ConversationHandler.END

    async def handle_remove_chat_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Remove the selected chat ID from the database."""
        query = update.callback_query
        await query.answer()
        chat_id_to_remove = query.data

        if chat_id_to_remove == settings.TELEGRAM_DEFAULT_CHAT_ID:
            await query.edit_message_text("❌ You cannot remove the default chat channel.")
        else:
            conn = database.create_bot_connection()
            try:
                repository.remove_chat(conn, chat_id_to_remove)
                await query.edit_message_text(f"✅ Chat ID &lt;code&gt;{chat_id_to_remove}&lt;/code&gt; has been removed.", parse_mode='HTML')
                logger.info(f"Admin {update.effective_user.id} removed chat ID {chat_id_to_remove}")
            finally:
                conn.close()

        await self.cmd_chats(update, context)
        return ConversationHandler.END
    
    # --- Other Admin Command Handlers ---

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔️ Unauthorized")
            return
        conn = database.create_bot_connection()
        try:
            stats = repository.get_today_stats(conn)
            is_active = repository.get_bot_state(conn)
            
            daily_limit_str = "Unlimited" if settings.MAX_SIGNALS_PER_DAY == 0 else str(settings.MAX_SIGNALS_PER_DAY)

            # --- Build the stats message dynamically ---
            message_lines = [
                "📊 <b>Trading Bot Statistics (Today)</b>",
                f"🔔 Signals: {stats['total_signals']}/{daily_limit_str}",
                f"📈 Buys: {stats['buys']}",
                f"📉 Sells: {stats['sells']}",
            ]

            # Only show P&L-related stats if at least one trade has been closed
            if stats['closed'] > 0:
                message_lines.extend([
                    f"✅ Closed: {stats['closed']}",
                    f"🏆 Wins: {stats['wins']}",
                    f"❌ Losses: {stats['losses']}",
                    f"💵 Total P&L: {stats['total_pl']:+.5f}"
                ])

            message_lines.append(f"🤖 Bot Status: {'🟢 Active' if is_active else '🔴 Paused'}")
            
            message = "\n".join(message_lines)
            # --- End of dynamic message build ---

            await update.message.reply_text(message, parse_mode='HTML')
        finally:
            conn.close()

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔️ Unauthorized")
            return
        conn = database.create_bot_connection()
        try:
            repository.set_bot_state(conn, active=False)
            await update.message.reply_text("⏸️ Bot paused. No new signals will be processed.")
            logger.info(f"Bot paused by admin {user_id}")
        finally:
            conn.close()

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔️ Unauthorized")
            return
        conn = database.create_bot_connection()
        try:
            repository.set_bot_state(conn, active=True)
            await update.message.reply_text("▶️ Bot resumed. Signals will be processed.")
            logger.info(f"Bot resumed by admin {user_id}")
        finally:
            conn.close()

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("⛔️ Unauthorized")
            return
        trading_hours = "24/7"
        if settings.TRADING_START_TIME and settings.TRADING_END_TIME:
            trading_hours = f"{settings.TRADING_START_TIME} - {settings.TRADING_END_TIME} UTC"
        help_text = f"""
🤖 <b>Trading Bot Admin Commands</b>
/stats - View today's statistics
/pause - Pause signal processing
/resume - Resume signal processing
/set - Interactively change a setting
/chats - Manage channels/groups receiving signals
/help - Show this help message
/cancel - Cancel an ongoing operation

<b>Current Rate Limits:</b>
• Max signals per day: {settings.MAX_SIGNALS_PER_DAY}
• Min time between signals: {settings.MIN_SECONDS_BETWEEN_SIGNALS}s
<b>Trading Hours:</b> {trading_hours}
"""
        await update.message.reply_text(help_text, parse_mode='HTML')

# Single instance of the service
telegram_service = TelegramService()
