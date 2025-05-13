# arbix_core/connectors/binance_connector.py
import configparser
import logging
from binance.client import Client
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

class BinanceConnector:
    def __init__(self, config_path='config/config.ini', testnet=True):
        config = configparser.ConfigParser()
        if not config.read(config_path):
            logger.error(f"Configuration file {config_path} not found or unreadable.")
            raise FileNotFoundError(f"Configuration file {config_path} not found.")

        self.api_key = config.get('BINANCE', 'api_key', fallback=None)
        self.api_secret = config.get('BINANCE', 'api_secret', fallback=None)
        self.testnet = testnet

        if not self.api_key or not self.api_secret:
            logger.error("Binance api_key or api_secret not found in config.")
            raise ValueError("Binance API credentials not configured.")

        self.client = None # This will be our main client instance
        # For compatibility with code expecting 'um_futures_client', we can alias it,
        # but it's the same object as self.client.
        self.um_futures_client = None 
        
        self._initialize_clients()

    def _initialize_clients(self):
        try:
            self.client = Client(self.api_key, self.api_secret)
            
            if self.testnet:
                # For v1.0.17, you set the testnet URLs directly on the client instance
                self.client.API_URL = 'https://testnet.binance.vision/api'  # Spot testnet base
                
                # The python-binance Client (v1.0.17) used these attributes internally for futures.
                # We need to ensure the config file has the correct futures testnet base URL.
                config = configparser.ConfigParser()
                config.read('config/config.ini') # Re-read for the specific URL if it's different
                
                # The library might use a variable like FUTURES_URL or similar,
                # or it might construct it from API_URL.
                # Forcing the base for futures on testnet is often done by setting these:
                # However, in v1.0.17, the testnet futures often required specific method parameters
                # or the library might have its own 'testnet=True' handling for futures.
                # Let's assume for now the main testnet setup for client covers it,
                # OR we confirm how futures testnet was targetted in 1.0.17.
                # A common way was to set the `FUTURES_URL`.
                
                # The library (python-binance v1.0.17) when calling futures_create_order, etc.,
                # would internally use a base URL. If testnet is desired for futures,
                # that base URL needs to be the testnet one.
                # This was often handled by client.FUTURES_URL, client.FUTURES_DATA_URL
                
                # Let's get the testnet futures URL from config:
                futures_testnet_url = config.get('BINANCE', 'testnet_futures_base_url', 
                                                 fallback='https://testnet.binancefuture.com')
                
                # In some older versions, you'd set these:
                self.client.FUTURES_URL = f"{futures_testnet_url}/fapi" # e.g. https://testnet.binancefuture.com/fapi
                self.client.FUTURES_DATA_URL = f"{futures_testnet_url}/futures/data" # e.g. https://testnet.binancefuture.com/futures/data
                # Note: The exact attribute names (FUTURES_URL) might vary slightly or be internal.
                # The most robust way for v1.0.17 testnet futures was often to use the `requests_params`
                # in Client init if the library didn't explicitly support a 'testnet' flag for futures.
                # However, your previous code used `self.client.FUTURES_URL = 'https://testnet.binancefuture.com'`
                # which implies this was a known way to do it.

                logger.info(f"Binance Client (v1.0.17) initialized. Attempting to set TESTNET URLs.")
                logger.info(f"Spot Testnet URL (API_URL): {self.client.API_URL}")
                if hasattr(self.client, 'FUTURES_URL'):
                    logger.info(f"Futures Testnet URL (FUTURES_URL): {self.client.FUTURES_URL}")
                else:
                    logger.warning("Client object does not have FUTURES_URL attribute. Futures testnet might not be configured correctly.")

            else: # Live environment
                # No specific URL changes needed for live, library defaults are usually correct.
                logger.info("Binance Client (v1.0.17) initialized for LIVE environment.")
            
            self.um_futures_client = self.client # Both point to the same object
            
            # Test connectivity using methods available on Client in v1.0.17
            self.ping_futures()
            self.get_futures_account_balance() # Ensure you have funds in testnet futures wallet
            
        except Exception as e:
            logger.error(f"Failed to initialize Binance client (v1.0.17): {e}", exc_info=True)

    def ping_futures(self):
        if not self.client:
            logger.warning("Binance client not initialized.")
            return None
        try:            # In v1.0.17, futures_ping was a method on the main Client
            self.client.futures_ping() 
            logger.info("Binance Futures API ping successful (using client.futures_ping).")
            return True
        except AttributeError:
            logger.error("Client object does not have 'futures_ping' attribute. (Likely version mismatch or issue)")
            return False
        except Exception as e:
            logger.error(f"Binance Futures API ping failed: {e}")
            return False    
            
    def get_futures_account_balance(self):
        if not self.client:
            logger.warning("Binance client not initialized.")
            return None
        try:
            response = self.client.futures_account(recvWindow=6000)
            balance_assets = response.get('assets', []) 
            logger.info("Successfully fetched Futures account details (using client.futures_account).")
            
            usdt_balance = next((item for item in balance_assets if item['asset'] == 'USDT'), None)
            if usdt_balance:
                logger.info(f"Futures USDT Balance from account details: {usdt_balance.get('walletBalance', 'N/A')}") 
            else:
                logger.info("No USDT balance found in futures account assets.")
            logger.debug(f"Full futures account assets response: {balance_assets}")
            return balance_assets
        except AttributeError:
            logger.error("Client object does not have 'futures_account' attribute.")
            return None
        except Exception as e:
            logger.error(f"Failed to get Futures account balance: {e}")
            return None

    def get_futures_server_time(self):
        if not self.client:
            logger.warning("Binance client not initialized.")
            return None
        try:
            time_res = self.client.futures_time() 
            logger.info(f"Binance Futures Server Time: {time_res['serverTime']} (using client.futures_time).")
            return time_res['serverTime']
        except AttributeError:
            logger.error("Client object does not have 'futures_time' attribute.")
            return None
        except Exception as e:
            logger.error(f"Failed to get Binance Futures server time: {e}")
            return None

    # --- Methods for futures klines, orders etc. will use self.client.futures_... methods ---
    def get_futures_klines_df(self, symbol: str, interval: str, start_time_ms: int = None, end_time_ms: int = None, limit: int = 500) -> pd.DataFrame | None:
        """
        Fetches historical klines for a symbol and returns them as a Pandas DataFrame.
        Uses client.futures_klines for python-binance v1.0.17.

        :param symbol: Trading symbol (e.g., "BTCUSDT")
        :param interval: Kline interval (e.g., "1m", "5m", "1h", "1d")
        :param start_time_ms: Optional start time in milliseconds (Binance epoch)
        :param end_time_ms: Optional end time in milliseconds (Binance epoch)
        :param limit: Max number of klines to fetch (default 500, max 1500 for some intervals/versions)
        :return: Pandas DataFrame with kline data, or None if an error occurs.
        """
        if not self.client:
            logger.warning("Binance client not initialized for get_futures_klines_df.")
            return None
        
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        if start_time_ms:
            params['startTime'] = start_time_ms
        if end_time_ms:
            params['endTime'] = end_time_ms

        try:
            # Method in v1.0.17 was client.futures_klines(...)
            # Docs for python-binance Client.futures_klines:
            # Klines are returned as a list of lists:
            # [
            #   [
            #     1499040000000,      // Kline open time
            #     "0.01634790",       // Open price
            #     "0.80000000",       // High price
            #     "0.01575800",       // Low price
            #     "0.01577100",       // Close price
            #     "148976.11427815",  // Volume
            #     1499644799999,      // Kline close time
            #     "2434.19055334",    // Quote asset volume
            #     308,                // Number of trades
            #     "1756.87402397",    // Taker buy base asset volume
            #     "28.46694368",      // Taker buy quote asset volume
            #     "17928899.62484339" // Ignore.
            #   ]
            # ]
            klines_raw = self.client.futures_klines(**params)
            if not klines_raw:
                logger.info(f"No klines returned for {symbol} {interval} with params {params}")
                return pd.DataFrame() # Return empty DataFrame

            df = pd.DataFrame(klines_raw, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])

            # Convert data types
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 
                            'quote_asset_volume', 'taker_buy_base_asset_volume', 
                            'taker_buy_quote_asset_volume']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col])
            
            df['number_of_trades'] = df['number_of_trades'].astype(int)

            # Set open_time as index
            df.set_index('open_time', inplace=True)
            
            # We might not need all columns, can drop 'ignore'
            df.drop(columns=['ignore'], inplace=True, errors='ignore')

            logger.info(f"Successfully fetched and processed {len(df)} klines for {symbol} {interval}.")
            return df

        except AttributeError:
            logger.error(f"Client object does not have 'futures_klines' attribute. (python-binance v1.0.17 expected)")
            return None
        except Exception as e:
            logger.error(f"Error fetching or processing futures klines for {symbol} {interval}: {e}", exc_info=True)
            return None
            
# Example usage:
# if __name__ == '__main__':
#     from arbix_core.utils.logger import setup_logging
#     # Adjust path if running directly
#     setup_logging(default_path='../../config/logging_config.json')
#
#     try:
#         # Ensure config/config.ini has TESTNET keys
#         # and testnet_futures_base_url = https://testnet.binancefuture.com
#         bn_connector = BinanceConnector(config_path='../../config/config.ini', testnet=True)
#         if bn_connector.client: # Check if client initialized
#             bn_connector.get_futures_account_balance()
#             klines = bn_connector.get_futures_klines(symbol="BTCUSDT", interval="1m", limit=5)
#             if klines:
#                 logger.info(f"Sample BTCUSDT 1m klines: {klines[:1]}") # Log first kline
#         else:
#             logger.error("Failed to create Binance connector (v1.0.17).")
#     except Exception as e:
#         logger.error(f"Error in BinanceConnector example: {e}")