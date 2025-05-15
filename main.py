import logging
import configparser
import asyncio
import pandas as pd 
from datetime import datetime 

from arbix_core.utils.logger import setup_logging
from arbix_core.connectors.telegram_bot import TelegramBot
from arbix_core.connectors.binance_connector import BinanceConnector

# Import the new strategy components
from arbix_core.strategy.example_strategy import SMACrossoverStrategy
from arbix_core.strategy.base_strategy import StrategySignal # For type hinting or direct use

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
    # Read use_testnet from config file
    try:
        use_testnet = config.getboolean('BINANCE', 'use_testnet', fallback=True)
    except configparser.NoSectionError:
        logger.warning("BINANCE section not found in config, defaulting use_testnet to True.")
        use_testnet = True
    except configparser.NoOptionError:
        logger.warning("use_testnet option not found in BINANCE section, defaulting to True.")
        use_testnet = True
        
    binance_connector = None
    try:
        binance_connector = BinanceConnector(config_path=config_path, testnet=use_testnet)
        if binance_connector.client: # Check if the underlying client in connector is initialized
            logger.info(f"Binance Connector initialized successfully. Testnet: {use_testnet}")
            if telegram_bot:
                server_time = binance_connector.get_futures_server_time()
                if server_time:
                    message_text = f"Binance Futures connection successful. Server Time: {server_time}"
                    await telegram_bot.send_message(message_text)
                else:
                    message_text = "Binance Futures connection successful, but couldn't fetch server time."
                    await telegram_bot.send_message(message_text)
        else:
            logger.error("Failed to initialize Binance client within the connector.")
            if telegram_bot:
                await telegram_bot.send_message("Error: Failed to initialize Binance client.")
            return # Critical: cannot proceed without Binance connection

    except FileNotFoundError:
        logger.critical("Binance config not found, connector not initialized.")
        if telegram_bot:
            await telegram_bot.send_message("CRITICAL Error: Binance configuration not found.")
        return
    except ValueError as ve: # Catches API key errors from BinanceConnector init
        logger.critical(f"ValueError during Binance Connector initialization: {ve}")
        if telegram_bot:
            await telegram_bot.send_message(f"CRITICAL Error: Binance API credentials missing or invalid: {str(ve)[:100]}")
        return
    except Exception as e: # Catch all other exceptions during BinanceConnector init
        logger.critical(f"Critical error initializing Binance Connector: {e}", exc_info=True)
        if telegram_bot:
            await telegram_bot.send_message(f"CRITICAL: Error initializing Binance Connector: {str(e)[:100]}")
        return
    
    # --- Klines Fetching Test (as you had it, can be kept or removed if strategy part covers it) ---
    # This section is now largely superseded by the strategy's kline fetching,
    # but kept for reference or if you want a direct kline fetch test separate from strategy.
    # You can comment it out if the strategy part is sufficient for your testing.
    
    # if binance_connector and binance_connector.client: 
    #     logger.info("Attempting to fetch klines (direct test)...")
    #     symbol_to_test_direct = config.get('TRADING', 'default_symbol_futures', fallback="BTCUSDT")
    #     kline_interval_direct = "1m"
    #     logger.info(f"Fetching latest 10 klines for {symbol_to_test_direct} {kline_interval_direct} (direct test).")
    #     klines_df_direct = binance_connector.get_futures_klines_df(
    #         symbol=symbol_to_test_direct, 
    #         interval=kline_interval_direct, 
    #         limit=10 
    #     )
    #     if klines_df_direct is not None and not klines_df_direct.empty:
    #         logger.info(f"Successfully fetched klines for {symbol_to_test_direct} (direct test):")
    #         logger.info(f"Head:\n{klines_df_direct.head().to_string()}")
    #         # ... (Telegram notification for direct kline test as you had) ...
    #     # ... (error handling for direct kline test as you had) ...


    # --- Strategy Initialization and Execution ---
    active_strategies = [] # To hold initialized strategy objects
    if binance_connector and binance_connector.client: # Ensure connector is up
        
        # Get strategy parameters from config
        symbol_to_trade = config.get('TRADING', 'default_symbol_futures', fallback="BTCUSDT")
        kline_interval_strategy = config.get('TRADING', 'default_kline_interval', fallback="1m")
        
        try:
            sma_short_window = config.getint('STRATEGY_SMA_CROSS', 'short_window', fallback=10)
            sma_long_window = config.getint('STRATEGY_SMA_CROSS', 'long_window', fallback=20)
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            logger.error(f"SMA Strategy configuration missing in config.ini ([STRATEGY_SMA_CROSS] section with short_window, long_window): {e}")
            if telegram_bot:
                await telegram_bot.send_message("Error: SMA Strategy config missing. Using defaults (10,20).")
            sma_short_window = 10 # Fallback defaults if config section is entirely missing
            sma_long_window = 20

        sma_strategy_config = {
            'short_window': sma_short_window,
            'long_window': sma_long_window
        }
        
        if sma_strategy_config['short_window'] >= sma_strategy_config['long_window']:
            logger.error(f"SMA Strategy config error: short_window ({sma_strategy_config['short_window']}) "
                         f"must be less than long_window ({sma_strategy_config['long_window']}). Adjust config.ini. Strategy not loaded.")
            if telegram_bot:
                await telegram_bot.send_message("Error: SMA Strategy config invalid (short >= long window). Strategy NOT loaded.")
        else:
            try:
                sma_strategy = SMACrossoverStrategy(
                    strategy_id=f"SMA_Cross_{symbol_to_trade}_{kline_interval_strategy}",
                    symbol=symbol_to_trade,
                    config=sma_strategy_config
                )
                active_strategies.append(sma_strategy)
                logger.info(f"Initialized strategy: {sma_strategy.get_name()} with ID: {sma_strategy.strategy_id} "
                            f"for {symbol_to_trade} {kline_interval_strategy} using windows "
                            f"({sma_strategy_config['short_window']},{sma_strategy_config['long_window']})")

                # Fetch enough klines for indicators
                # Need at least long_window candles +1 for prev, +1 for current, so long_window + 2.
                # Fetching more (e.g., long_window * 2 or a fixed number like 50-100) is safer for stability.
                num_klines_to_fetch = sma_strategy_config['long_window'] + 30 # Fetch ample buffer
                
                logger.info(f"Fetching initial {num_klines_to_fetch} klines for strategy {sma_strategy.strategy_id}...")
                initial_klines_df = binance_connector.get_futures_klines_df(
                    symbol=symbol_to_trade,
                    interval=kline_interval_strategy,
                    limit=num_klines_to_fetch
                )

                if initial_klines_df is not None and not initial_klines_df.empty:
                    logger.info(f"Successfully fetched {len(initial_klines_df)} initial klines for strategy {sma_strategy.strategy_id}.")
                    
                    sma_strategy.update_data(initial_klines_df) # Feed data to the strategy
                    signal_object = sma_strategy.run()          # Run the strategy to get a signal

                    if signal_object and isinstance(signal_object, StrategySignal):
                        logger.info(f"Strategy {sma_strategy.strategy_id} generated initial signal: {signal_object.signal_type} - Details: {signal_object.details}")
                        if telegram_bot:
                            # Format details for telegram message
                            details_str_parts = []
                            if 'price_at_signal' in signal_object.details:
                                details_str_parts.append(f"Price: {signal_object.details['price_at_signal']:.4f}")
                            if 'short_sma' in signal_object.details:
                                details_str_parts.append(f"SMA Short: {signal_object.details['short_sma']:.4f}")
                            if 'long_sma' in signal_object.details:
                                details_str_parts.append(f"SMA Long: {signal_object.details['long_sma']:.4f}")
                            if 'reason' in signal_object.details:
                                details_str_parts.append(f"Reason: {signal_object.details['reason']}")
                            
                            details_for_tg = "\n".join(details_str_parts)

                            await telegram_bot.send_message(
                                f"Strategy: {sma_strategy.strategy_id}\n"
                                f"Symbol: {signal_object.symbol}\n"
                                f"Signal: {signal_object.signal_type}\n"
                                f"{details_for_tg}"
                            )
                    else:
                        logger.warning(f"Strategy {sma_strategy.strategy_id} did not generate a valid signal object on initial run. Received: {signal_object}")
                        if telegram_bot:
                            await telegram_bot.send_message(f"Warning: Strategy {sma_strategy.strategy_id} on {symbol_to_trade} "
                                                            f"returned an invalid/no signal object on initial run.")

                else: # Failed to get initial klines for strategy
                    logger.error(f"Failed to fetch initial klines for strategy {sma_strategy.strategy_id}. Strategy cannot run.")
                    if telegram_bot:
                        await telegram_bot.send_message(f"Error: Failed to fetch initial klines for {symbol_to_trade}. "
                                                        f"Strategy {sma_strategy.strategy_id} cannot start.")
            
            except ValueError as ve: # Catches strategy-specific init errors like bad window sizes
                 logger.error(f"Error initializing SMACrossoverStrategy: {ve}", exc_info=True)
                 if telegram_bot:
                     await telegram_bot.send_message(f"Error: Failed to initialize SMA Strategy for {symbol_to_trade}: {str(ve)[:100]}")
            except Exception as e: # Catch-all for other strategy loading/running issues
                 logger.error(f"Unexpected error during strategy setup/run for {symbol_to_trade}: {e}", exc_info=True)
                 if telegram_bot:
                     await telegram_bot.send_message(f"Error: Unexpected issue with strategy for {symbol_to_trade}: {str(e)[:100]}")
    
    else: # Binance connector failed earlier
        logger.error("Binance connector not available. Cannot initialize or run strategies.")
        if telegram_bot: await telegram_bot.send_message("Error: Binance connector failed. Strategies not running.")


    logger.info("Arbix application setup complete. Entering main loop (not yet implemented)...")
    if telegram_bot:
        message_text = f"{project_name} main process finished setup phase."
        await telegram_bot.send_message(message_text)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arbix application shutting down by user request (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True) # Log full traceback for unhandled
    finally:
        logging.info("Arbix application stopped.")