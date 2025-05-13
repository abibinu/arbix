import logging
import configparser
import asyncio
import pandas as pd 
from datetime import datetime 

from arbix_core.utils.logger import setup_logging
# from arbix_core.utils.telegram_utils import escape_markdown_v2 # No longer needed here if escape is in TelegramBot class
from arbix_core.connectors.telegram_bot import TelegramBot
from arbix_core.connectors.binance_connector import BinanceConnector

# Setup logging first
setup_logging(default_path='config/logging_config.json')
logger = logging.getLogger(__name__)

async def main():
    logger.info("Starting Arbix application...")

    # Load main configuration
    config = configparser.ConfigParser()
    config_path = 'config/config.ini'
    if not config.read(config_path):
        logger.critical(f"CRITICAL: Configuration file {config_path} not found. Exiting.")
        return
    
    project_name = config.get('DEFAULT', 'project_name', fallback="Arbix")
    logger.info(f"Welcome to {project_name}!")

    # Initialize Telegram Bot
    telegram_bot = None
    try:
        telegram_bot = TelegramBot(config_path=config_path)
        message_text = f"{project_name} instance started successfully."
        await telegram_bot.send_message(message_text) # Assumes escaping is done within TelegramBot
    except FileNotFoundError:
        logger.error("Telegram config not found, bot not initialized.")
    except Exception as e:
        logger.error(f"Error initializing or sending message with Telegram Bot: {e}")

    # Initialize Binance Connector
    use_testnet = True # Or read from config
    binance_connector = None
    try:
        binance_connector = BinanceConnector(config_path=config_path, testnet=use_testnet)
        if binance_connector.client: # Check if the underlying client in connector is initialized
            logger.info("Binance Connector initialized successfully.")
            if telegram_bot:
                server_time = binance_connector.get_futures_server_time()
                if server_time:
                    # Convert server_time (milliseconds) to a readable string if desired for the message
                    # readable_time = datetime.fromtimestamp(int(server_time)/1000).strftime('%Y-%m-%d %H:%M:%S UTC')
                    message_text = f"Binance Futures connection successful. Server Time: {server_time}"
                    await telegram_bot.send_message(message_text)
                else:
                    message_text = "Binance Futures connection successful, but couldn't fetch server time."
                    await telegram_bot.send_message(message_text)
        else:
            logger.error("Failed to initialize Binance client within the connector.")
            if telegram_bot:
                await telegram_bot.send_message("Error: Failed to initialize Binance client.")

    except FileNotFoundError:
        logger.critical("Binance config not found, connector not initialized.")
        if telegram_bot:
            await telegram_bot.send_message("CRITICAL Error: Binance configuration not found.")
        return
    except ValueError as ve:
        logger.critical(f"ValueError during Binance Connector initialization: {ve}")
        if telegram_bot:
            await telegram_bot.send_message("CRITICAL Error: Binance API credentials missing or invalid.")
        return
    except Exception as e:
        logger.error(f"Error initializing Binance Connector: {e}")
        if telegram_bot:
            await telegram_bot.send_message(f"Error: Could not initialize Binance Connector: {e}")
    
    if binance_connector and binance_connector.client: # Check if client exists
        logger.info("Attempting to fetch klines...")
        # Test fetching klines
        # You might need to provide a valid symbol for the testnet
        # Common testnet symbols: BTCUSDT, ETHUSDT
        # Make sure testnet_futures_base_url is https://testnet.binancefuture.com in config
        
        symbol_to_test = config.get('TRADING', 'default_symbol_futures', fallback="BTCUSDT")
        kline_interval = "1m"
        
        # To get klines for a specific recent period (e.g., last few hours)
        # Use this if you want to test fetching with start_time_ms
        # now_ms = int(datetime.now().timestamp() * 1000)
        # start_ms = now_ms - (10 * 60 * 1000) # 10 minutes ago, for a small test
        # logger.info(f"Fetching klines for {symbol_to_test} from {datetime.fromtimestamp(start_ms/1000)} with limit 10.")
        # klines_df = binance_connector.get_futures_klines_df(
        #     symbol=symbol_to_test, 
        #     interval=kline_interval, 
        #     start_time_ms=start_ms, 
        #     limit=10 # Test with a small limit
        # )

        # Simpler: get latest N klines (most common use for live data, less common for historical)
        # For testing the function, fetching latest N is fine.
        logger.info(f"Fetching latest 10 klines for {symbol_to_test} {kline_interval}.")
        klines_df = binance_connector.get_futures_klines_df(
            symbol=symbol_to_test, 
            interval=kline_interval, 
            limit=10 
        )

        if klines_df is not None and not klines_df.empty:
            logger.info(f"Successfully fetched klines for {symbol_to_test}:")
            # Log head and tail to see the range if fetching more data
            logger.info(f"Head:\n{klines_df.head().to_string()}")
            logger.info(f"Tail:\n{klines_df.tail().to_string()}")
            
            if telegram_bot:
                # Ensure the message is not too long for Telegram
                last_close_price = klines_df['close'].iloc[-1]
                first_open_time = klines_df.index[0].strftime('%Y-%m-%d %H:%M')
                last_close_time = klines_df['close_time'].iloc[-1].strftime('%Y-%m-%d %H:%M')

                message = (f"Fetched {len(klines_df)} klines for {symbol_to_test} {kline_interval}. "
                           f"Data from {first_open_time} to {last_close_time}. "
                           f"Last close: {last_close_price}")
                await telegram_bot.send_message(message)
        elif klines_df is not None and klines_df.empty: # Check for empty DataFrame specifically
            logger.info(f"No klines returned for {symbol_to_test} {kline_interval} (empty DataFrame).")
            if telegram_bot:
                await telegram_bot.send_message(f"No klines data returned for {symbol_to_test} {kline_interval}.")
        else: # klines_df is None, indicating an error during fetch/process
            logger.error(f"Failed to fetch klines for {symbol_to_test}.")
            if telegram_bot:
                await telegram_bot.send_message(f"Error fetching klines for {symbol_to_test} {kline_interval}.")

    # --- Placeholder for future logic ---
    logger.info("Arbix application setup complete. Entering main loop (not yet implemented)...")
    # For now, we just exit after setup
    if telegram_bot:
        message_text = f"{project_name} main process finished setup phase."
        await telegram_bot.send_message(message_text)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arbix application shutting down by user request (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
    finally:
        logging.info("Arbix application stopped.")