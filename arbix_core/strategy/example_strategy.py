# arbix_core/strategy/example_strategy.py
import pandas as pd
import logging
from .base_strategy import BaseStrategy, StrategySignal

# Attempt to import 'ta' library, fall back to basic pandas rolling if not available
try:
    from ta.trend import SMAIndicator
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    logger = logging.getLogger(__name__) # Define logger if ta fails, base_strategy already defines it
    logger.warning("The 'ta' library is not installed. SMA calculations will use basic pandas rolling mean. "
                   "Install with 'pip install ta'.")


logger = logging.getLogger(__name__) # Will be arbix_core.strategy.example_strategy

class SMACrossoverStrategy(BaseStrategy):
    """
    A simple Moving Average (MA) Crossover strategy.
    - Generates a BUY signal when the short-term MA crosses above the long-term MA.
    - Generates a SELL signal when the short-term MA crosses below the long-term MA.
    """

    def __init__(self, strategy_id: str, symbol: str, config: dict = None):
        super().__init__(strategy_id, symbol, config)
        # Default configuration for SMA periods
        self.short_window = self.config.get('short_window', 20) # e.g., 20 periods
        self.long_window = self.config.get('long_window', 50)   # e.g., 50 periods
        
        if self.short_window >= self.long_window:
            raise ValueError("Short window must be less than long window for SMA Crossover.")
        
        logger.info(f"SMACrossoverStrategy [{self.strategy_id}] for [{self.symbol}] initialized with "
                    f"short_window={self.short_window}, long_window={self.long_window}. TA library available: {TA_AVAILABLE}")

    def calculate_indicators(self, klines_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates short-term and long-term Simple Moving Averages (SMA).
        """
        if klines_df.empty or len(klines_df) < self.long_window:
            logger.warning(f"Strategy [{self.strategy_id}] for [{self.symbol}]: Not enough data points "
                           f"({len(klines_df)}) to calculate SMAs requiring {self.long_window} periods. Skipping indicator calculation.")
            return klines_df # Return original df, or an empty one if preferred when insufficient data

        # Ensure 'close' column exists and is numeric
        if 'close' not in klines_df.columns or not pd.api.types.is_numeric_dtype(klines_df['close']):
            logger.error(f"Strategy [{self.strategy_id}] for [{self.symbol}]: 'close' column is missing or not numeric.")
            return pd.DataFrame() # Return empty df to signal error

        if TA_AVAILABLE:
            # Using 'ta' library
            sma_short_indicator = SMAIndicator(close=klines_df['close'], window=self.short_window, fillna=False)
            klines_df[f'sma_short_{self.short_window}'] = sma_short_indicator.sma_indicator()

            sma_long_indicator = SMAIndicator(close=klines_df['close'], window=self.long_window, fillna=False)
            klines_df[f'sma_long_{self.long_window}'] = sma_long_indicator.sma_indicator()
        else:
            # Using basic pandas rolling mean
            klines_df[f'sma_short_{self.short_window}'] = klines_df['close'].rolling(window=self.short_window).mean()
            klines_df[f'sma_long_{self.long_window}'] = klines_df['close'].rolling(window=self.long_window).mean()
        
        logger.debug(f"Strategy [{self.strategy_id}] for [{self.symbol}]: SMAs calculated. "
                     f"Last short SMA: {klines_df[f'sma_short_{self.short_window}'].iloc[-1]}, "
                     f"Last long SMA: {klines_df[f'sma_long_{self.long_window}'].iloc[-1]}")
        return klines_df

    def generate_signal(self, klines_with_indicators: pd.DataFrame) -> StrategySignal:
        """
        Generates BUY or SELL signal based on SMA crossover.
        Looks at the last two candles to confirm a crossover.
        """
        signal_type = "NO_SIGNAL"
        details = {}

        short_sma_col = f'sma_short_{self.short_window}'
        long_sma_col = f'sma_long_{self.long_window}'

        # Ensure indicator columns exist
        if short_sma_col not in klines_with_indicators.columns or long_sma_col not in klines_with_indicators.columns:
            logger.error(f"Strategy [{self.strategy_id}] for [{self.symbol}]: SMA columns not found in DataFrame. Cannot generate signal.")
            return StrategySignal("NO_SIGNAL", self.symbol, {"reason": "SMA columns missing"})

        # Need at least 2 rows to check for a crossover from the previous period
        if len(klines_with_indicators) < 2:
            logger.warning(f"Strategy [{self.strategy_id}] for [{self.symbol}]: Not enough data rows ({len(klines_with_indicators)}) "
                           f"to check for crossover. Need at least 2.")
            return StrategySignal("NO_SIGNAL", self.symbol, {"reason": "Insufficient rows for crossover check"})

        # Get the last two rows for crossover detection
        # .iloc[-1] is the current (latest) candle
        # .iloc[-2] is the previous candle
        last_row = klines_with_indicators.iloc[-1]
        prev_row = klines_with_indicators.iloc[-2]

        # Check for NaN values in SMAs for the relevant rows
        if pd.isna(last_row[short_sma_col]) or pd.isna(last_row[long_sma_col]) or \
           pd.isna(prev_row[short_sma_col]) or pd.isna(prev_row[long_sma_col]):
            logger.warning(f"Strategy [{self.strategy_id}] for [{self.symbol}]: NaN values in SMAs for last or previous period. Cannot generate signal.")
            return StrategySignal("NO_SIGNAL", self.symbol, {"reason": "NaN in SMA values"})

        # Current candle values
        current_short_sma = last_row[short_sma_col]
        current_long_sma = last_row[long_sma_col]

        # Previous candle values
        prev_short_sma = prev_row[short_sma_col]
        prev_long_sma = prev_row[long_sma_col]

        # Bullish Crossover: Short SMA crosses above Long SMA
        # Previous: short <= long
        # Current:  short > long
        if prev_short_sma <= prev_long_sma and current_short_sma > current_long_sma:
            signal_type = "BUY"
            details['reason'] = f"Bullish Crossover: Short SMA ({current_short_sma:.4f}) crossed above Long SMA ({current_long_sma:.4f})"
            details['price_at_signal'] = last_row['close'] # Signal based on close of current candle
            details['short_sma'] = current_short_sma
            details['long_sma'] = current_long_sma
            logger.info(f"Strategy [{self.strategy_id}] for [{self.symbol}]: BUY signal generated. {details['reason']}")

        # Bearish Crossover: Short SMA crosses below Long SMA
        # Previous: short >= long
        # Current:  short < long
        elif prev_short_sma >= prev_long_sma and current_short_sma < current_long_sma:
            signal_type = "SELL" # For futures, this could mean open SHORT position
            details['reason'] = f"Bearish Crossover: Short SMA ({current_short_sma:.4f}) crossed below Long SMA ({current_long_sma:.4f})"
            details['price_at_signal'] = last_row['close']
            details['short_sma'] = current_short_sma
            details['long_sma'] = current_long_sma
            logger.info(f"Strategy [{self.strategy_id}] for [{self.symbol}]: SELL signal generated. {details['reason']}")
        else:
            signal_type = "HOLD" # No crossover event, maintain current position or do nothing
            details['reason'] = "No crossover event."
            details['short_sma'] = current_short_sma
            details['long_sma'] = current_long_sma
            # logger.debug(f"Strategy [{self.strategy_id}] for [{self.symbol}]: HOLD signal. {details['reason']}")


        return StrategySignal(signal_type, self.symbol, details)