import telegram
import configparser
import logging
import asyncio 

logger = logging.getLogger(__name__) # Will be arbix_core.connectors.telegram_bot if setup_logging is called first

class TelegramBot:
    def __init__(self, config_path='config/config.ini'):
        config = configparser.ConfigParser()
        if not config.read(config_path):
            logger.error(f"Configuration file {config_path} not found or unreadable.")
            raise FileNotFoundError(f"Configuration file {config_path} not found.")

        self.bot_token = config.get('TELEGRAM', 'bot_token', fallback=None)
        self.chat_id = config.get('TELEGRAM', 'chat_id', fallback=None)

        if not self.bot_token or not self.chat_id:
            logger.error("Telegram bot_token or chat_id not found in config.")
            # Optionally, allow operation without Telegram if not configured
            self.bot = None
        else:
            try:
                self.bot = telegram.Bot(token=self.bot_token)
                logger.info("Telegram Bot initialized successfully.")
            except Exception as e:                
                logger.error(f"Failed to initialize Telegram Bot: {e}")
                self.bot = None

    def escape_markdown_v2(self, text: str) -> str:
        """Escape special characters for Telegram MarkdownV2 format"""
        # First escape the backslash itself
        text = text.replace('\\', '\\\\')
        # Characters that need escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
        escape_chars = '_*[]()~`>#+-=|{}.!'
        # Then escape all other special characters
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text

    async def send_message(self, message: str):
        if self.bot and self.chat_id:
            try:
                # Escape the message for MarkdownV2
                escaped_message = self.escape_markdown_v2(message)
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=escaped_message,
                    parse_mode='MarkdownV2'
                )
                logger.debug(f"Telegram message sent: {message[:50]}...") # Log only part of the message
            except Exception as e:
                logger.error(f"Failed to send Telegram message: {e}")
        else:
            logger.warning(f"Telegram bot not configured or initialized. Message not sent: {message[:50]}...")

    # Synchronous wrapper for convenience if not in an async context
    def send_message_sync(self, message: str):
        if self.bot and self.chat_id:
            try:
                # For synchronous calls, we create a new event loop
                # This is not ideal for frequent calls from a sync context in an async app
                # Best to call send_message from an async function
                asyncio.run(self.send_message(message))
            except RuntimeError as e:
                # If already in an event loop (e.g., Jupyter notebook), this can happen
                logger.error(f"RuntimeError sending sync message (possibly nested event loops): {e}. Message not sent.")
            except Exception as e:
                logger.error(f"Failed to send sync Telegram message: {e}")
        else:
            logger.warning(f"Telegram bot not configured or initialized. Message not sent: {message[:50]}...")


# Example usage (can be moved to a test file or main.py)
# if __name__ == '__main__':
#     from arbix_core.utils.logger import setup_logging
#     setup_logging(default_path='../../config/logging_config.json') # Adjust path for direct execution
#
#     async def main_async():
#         bot = TelegramBot(config_path='../../config/config.ini') # Adjust path
#         await bot.send_message("Hello from Arbix\\! Test message from `telegram_bot.py` \\(async\\)\\.")
#         # Example of MarkdownV2 special characters: . ! - # ( ) [ ] { } > + _ * `
#         # Needs to be escaped with \
#
#     # asyncio.run(main_async())
#
#     # Synchronous example
#     bot_sync = TelegramBot(config_path='../../config/config.ini')
#     bot_sync.send_message_sync("Hello from Arbix\\! Test message from `telegram_bot.py` \\(sync\\)\\.")