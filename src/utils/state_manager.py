"""Centralized state management for the bot, using SQLite backend."""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
import asyncio # Keep for potential async operations like model validation

# Import the new DatabaseManager
from .database import DatabaseManager
# Keep config import for default values if DB is empty
from ..config import (
    DEFAULT_MODEL as CONFIG_DEFAULT_MODEL,
    INTENT_DISCOVERY as CONFIG_INTENT_DISCOVERY,
    INTENT_DETECTION_MODEL as CONFIG_INTENT_MODEL,
    INTENT_CONFIDENCE_THRESHOLD as CONFIG_INTENT_THRESHOLD
)

logger = logging.getLogger('state_manager')

# --- Constants for DB keys ---
# These help avoid typos when accessing global config in the DB
CONFIG_KEY_MAX_HISTORY = "max_channel_history"
CONFIG_KEY_TIME_WINDOW = "time_window_hours"
CONFIG_KEY_GLOBAL_MODEL = "global_model"
CONFIG_KEY_GLOBAL_PROVIDER = "global_provider"
CONFIG_KEY_GLOBAL_SYSTEM_PROMPT = "global_system_prompt"
CONFIG_KEY_PRUNE_FREQUENCY_HOURS = "prune_frequency_hours"
CONFIG_KEY_INTENT_ENABLED = "intent_enabled"
CONFIG_KEY_INTENT_MODEL = "intent_model"
CONFIG_KEY_INTENT_THRESHOLD = "intent_threshold"

class BotStateManager:
    """Singleton class to manage shared state via DatabaseManager."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BotStateManager, cls).__new__(cls)
            # Initialization moved to a separate async method to handle potential async loads
            # cls._instance._initialize() # Removed sync initialization
            logger.info(f"Created new BotStateManager instance placeholder with id: {id(cls._instance)}")
        else:
            logger.info(f"Reusing existing BotStateManager instance with id: {id(cls._instance)}")
        return cls._instance

    async def initialize_state(self):
        """Asynchronously initializes the state manager and database connection."""
        if hasattr(self, '_initialized') and self._initialized:
            logger.info("StateManager already initialized.")
            return

        logger.info(f"Initializing BotStateManager instance with id: {id(self)}")
        self.db_manager = DatabaseManager() # Initialize DB connection and schema
        self.model_manager = None # Placeholder for ModelManager instance

        # Load configuration from DB or set defaults
        self.max_channel_history = await self._load_or_set_config(CONFIG_KEY_MAX_HISTORY, 35, 'int')
        self.time_window_hours = await self._load_or_set_config(CONFIG_KEY_TIME_WINDOW, 48, 'int')
        self.global_model = await self._load_or_set_config(CONFIG_KEY_GLOBAL_MODEL, CONFIG_DEFAULT_MODEL, 'string')
        self.global_provider = await self._load_or_set_config(CONFIG_KEY_GLOBAL_PROVIDER, "openrouter", 'string')
        self.global_system_prompt = await self._load_or_set_config(CONFIG_KEY_GLOBAL_SYSTEM_PROMPT, None, 'string')
        self.prune_frequency_hours = await self._load_or_set_config(CONFIG_KEY_PRUNE_FREQUENCY_HOURS, 24, 'int')

        # Intent detection settings - load from DB or use .env defaults
        self.intent_enabled = await self._load_or_set_config(CONFIG_KEY_INTENT_ENABLED, CONFIG_INTENT_DISCOVERY, 'bool')
        self.intent_model = await self._load_or_set_config(CONFIG_KEY_INTENT_MODEL, CONFIG_INTENT_MODEL, 'string')
        self.intent_threshold = await self._load_or_set_config(CONFIG_KEY_INTENT_THRESHOLD, CONFIG_INTENT_THRESHOLD, 'float')

        self._initialized = True
        logger.info("BotStateManager initialized successfully.")

    async def reinitialize_state(self):
        """Re-reads all configuration from the database into memory.

        Called after config import or database restore to pick up new values
        without requiring a bot restart.
        """
        logger.info("Reinitializing BotStateManager from database...")
        self._initialized = False
        await self.initialize_state()

    async def _load_or_set_config(self, key: str, default_value: Any, value_type: str) -> Any:
        """Loads config from DB or sets default if not found."""
        value = self.db_manager.get_global_config(key)
        if value is None:
            logger.info(f"Config key '{key}' not found in DB, setting default: {default_value}")
            # Handle None default value correctly
            if default_value is not None:
                 self.db_manager.set_global_config(key, default_value, value_type)
                 return default_value
            else:
                 # If default is None, we don't necessarily want to store 'None' string unless type is string
                 if value_type == 'string':
                     self.db_manager.set_global_config(key, None, value_type)
                 # For other types, maybe don't store None? Or store a specific representation?
                 # For now, just return None without storing if default is None and type isn't string.
                 return None
        else:
            # Ensure the type matches what we expect, log warning if not?
            # For now, assume the type in DB is correct.
            return value

    def set_model_manager(self, model_manager):
        """Sets the ModelManager instance, used for model validation."""
        self.model_manager = model_manager
        logger.info(f"ModelManager instance set for BotStateManager: {id(model_manager)}")

    def close_db(self):
        """Closes the database connection."""
        if hasattr(self, 'db_manager') and self.db_manager:
            self.db_manager.close()

    # --- Configuration Methods ---

    def get_max_channel_history(self) -> int:
        return self.max_channel_history

    async def set_max_channel_history(self, value: int):
        self.max_channel_history = value
        await self._save_config(CONFIG_KEY_MAX_HISTORY, value, 'int')

    def get_time_window_hours(self) -> int:
        return self.time_window_hours

    async def set_time_window_hours(self, value: int):
        self.time_window_hours = value
        await self._save_config(CONFIG_KEY_TIME_WINDOW, value, 'int')

    def get_prune_frequency_hours(self) -> int:
        return self.prune_frequency_hours

    async def set_prune_frequency_hours(self, value: int):
        if value < 1:
            raise ValueError("Pruning frequency must be at least 1 hour.")
        self.prune_frequency_hours = value
        await self._save_config(CONFIG_KEY_PRUNE_FREQUENCY_HOURS, value, 'int')

    # --- Intent Detection Methods ---

    def get_intent_enabled(self) -> bool:
        """Gets whether intent detection is enabled."""
        return self.intent_enabled

    async def set_intent_enabled(self, value: bool):
        """Sets whether intent detection is enabled."""
        self.intent_enabled = value
        await self._save_config(CONFIG_KEY_INTENT_ENABLED, value, 'bool')
        logger.info(f"Intent detection {'enabled' if value else 'disabled'}")

    def get_intent_model(self) -> str:
        """Gets the intent detection model."""
        return self.intent_model

    async def set_intent_model(self, model: str):
        """Sets the intent detection model after validation."""
        if not self.model_manager:
            raise RuntimeError("ModelManager not set in BotStateManager")

        # Parse and validate the model ID format
        provider, model_name = self.model_manager.parse_model_id(model)
        canonical_model_id = f"{provider}/{model_name}"

        # Force refresh models for the parsed provider before validation
        await self.model_manager.get_models(provider, force_refresh=True)

        # Validate the canonical model ID
        is_valid = await self.model_manager.is_valid_model(canonical_model_id)
        if not is_valid:
            # Fetch models for the specific provider for the error message
            provider_models = []
            try:
                models = await self.model_manager.get_models(provider, force_refresh=False)
                provider_models = [f"{provider}/{m}" for m in models]
            except Exception as ex:
                logger.warning(f"Could not fetch models for provider {provider} for error message: {ex}")

            allowed_str = ', '.join(provider_models[:10]) + ('...' if len(provider_models) > 10 else '')
            raise ValueError(f"Model '{canonical_model_id}' not found for provider '{provider}'. Allowed: {allowed_str}")

        self.intent_model = canonical_model_id
        await self._save_config(CONFIG_KEY_INTENT_MODEL, canonical_model_id, 'string')
        logger.info(f"Intent detection model set to: {canonical_model_id}")

    def get_intent_threshold(self) -> float:
        """Gets the intent confidence threshold."""
        return self.intent_threshold

    async def set_intent_threshold(self, value: float):
        """Sets the intent confidence threshold (0.0-1.0)."""
        if value < 0.0 or value > 1.0:
            raise ValueError("Intent threshold must be between 0.0 and 1.0")
        self.intent_threshold = value
        await self._save_config(CONFIG_KEY_INTENT_THRESHOLD, value, 'float')
        logger.info(f"Intent confidence threshold set to: {value}")

    async def reload_intent_from_env(self):
        """Reloads intent settings from environment variables."""
        self.intent_enabled = CONFIG_INTENT_DISCOVERY
        self.intent_model = CONFIG_INTENT_MODEL
        self.intent_threshold = CONFIG_INTENT_THRESHOLD
        # Save to DB
        await self._save_config(CONFIG_KEY_INTENT_ENABLED, self.intent_enabled, 'bool')
        await self._save_config(CONFIG_KEY_INTENT_MODEL, self.intent_model, 'string')
        await self._save_config(CONFIG_KEY_INTENT_THRESHOLD, self.intent_threshold, 'float')
        logger.info(f"Intent settings reloaded from .env: enabled={self.intent_enabled}, model={self.intent_model}, threshold={self.intent_threshold}")

    async def reload_all_from_env(self, system_prompt: str) -> dict:
        """Reloads all settings from environment variables. Returns dict of reloaded values."""
        # Reimport config to get fresh values (in case .env was modified)
        from ..config import (
            DEFAULT_MODEL,
            INTENT_DISCOVERY,
            INTENT_DETECTION_MODEL,
            INTENT_CONFIDENCE_THRESHOLD
        )

        # Reload global model
        self.global_model = DEFAULT_MODEL
        await self._save_config(CONFIG_KEY_GLOBAL_MODEL, self.global_model, 'string')

        # Reload memory and time window to defaults from initialization
        self.max_channel_history = 35
        self.time_window_hours = 48
        await self._save_config(CONFIG_KEY_MAX_HISTORY, self.max_channel_history, 'int')
        await self._save_config(CONFIG_KEY_TIME_WINDOW, self.time_window_hours, 'int')

        # Reload system prompt (passed in since it comes from config)
        await self.set_global_system_prompt(system_prompt)

        # Reload intent settings
        self.intent_enabled = INTENT_DISCOVERY
        self.intent_model = INTENT_DETECTION_MODEL
        self.intent_threshold = INTENT_CONFIDENCE_THRESHOLD
        await self._save_config(CONFIG_KEY_INTENT_ENABLED, self.intent_enabled, 'bool')
        await self._save_config(CONFIG_KEY_INTENT_MODEL, self.intent_model, 'string')
        await self._save_config(CONFIG_KEY_INTENT_THRESHOLD, self.intent_threshold, 'float')

        logger.info(f"All settings reloaded from .env")

        return {
            "global_model": self.global_model,
            "max_channel_history": self.max_channel_history,
            "time_window_hours": self.time_window_hours,
            "intent_enabled": self.intent_enabled,
            "intent_model": self.intent_model,
            "intent_threshold": self.intent_threshold
        }


    async def _save_config(self, key: str, value: Any, value_type: str):
        """Saves a configuration value to the database."""
        # This can remain synchronous if db_manager methods are sync
        self.db_manager.set_global_config(key, value, value_type)

    def get_global_config(self, key: str, default: Any = None) -> Any:
        """Gets a global configuration value from the database."""
        return self.db_manager.get_global_config(key, default)

    def set_global_config(self, key: str, value: Any, value_type: str):
        """Sets a global configuration value in the database."""
        self.db_manager.set_global_config(key, value, value_type)

    # --- Channel History Methods ---

    def get_channel_history(self, channel_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Gets message history for a channel from the database."""
        # Use configured history limit if no specific limit is passed
        effective_limit = limit if limit is not None else self.max_channel_history
        # Pass time window limit as well? Or rely on pruning? Let's rely on pruning for now.
        return self.db_manager.get_channel_history(str(channel_id), limit=effective_limit)

    async def add_to_channel_history(self, channel_id: str, message: Dict[str, Any]):
        """Adds a message to the channel history in the database."""
        # Extract relevant fields from the message dict
        role = message.get("role")
        content = message.get("content")
        user_id = message.get("user_id") # Assuming user_id might be in the message dict
        timestamp = datetime.now() # Use current time for DB timestamp

        if not role or not content:
             logger.error(f"Message missing role or content: {message}")
             return # Don't add incomplete messages

        # Database call is synchronous
        self.db_manager.add_message(
            role=role,
            content=content,
            timestamp=timestamp,
            channel_id=str(channel_id),
            user_id=user_id
        )

    def clear_channel_history(self, channel_id: str) -> bool:
        """Clears history for a channel by deleting messages from the database."""
        # This is potentially dangerous. Maybe implement soft delete or archiving later?
        # For now, it directly deletes.
        sql = "DELETE FROM MESSAGES WHERE channel_id = ?;"
        try:
            with self.db_manager._conn: # Access connection directly for transaction
                cursor = self.db_manager._get_cursor()
                cursor.execute(sql, (str(channel_id),))
                deleted_count = cursor.rowcount
            logger.info(f"Cleared {deleted_count} messages for channel {channel_id}")
            return deleted_count > 0
        except sqlite3.Error as e:
            logger.error(f"Error clearing history for channel '{channel_id}': {e}", exc_info=True)
            return False

    # --- Discord Thread Methods ---

    async def add_discord_thread(self, thread_id: str, channel_id: str, name: str):
        """Adds a thread record to the database."""
        # Database call is synchronous
        self.db_manager.add_thread(
            thread_id=str(thread_id),
            channel_id=str(channel_id),
            name=name,
            created_at=datetime.now()
        )

    async def add_discord_thread_message(self, thread_id: str, message: Dict[str, Any]):
        """Adds a message associated with a thread to the database."""
        role = message.get("role")
        content = message.get("content")
        user_id = message.get("user_id")
        timestamp = datetime.now()

        if not role or not content:
             logger.error(f"Thread message missing role or content: {message}")
             return

        # Database call is synchronous
        self.db_manager.add_message(
            role=role,
            content=content,
            timestamp=timestamp,
            thread_id=str(thread_id),
            user_id=user_id
        )

    def get_discord_thread_history(self, thread_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Gets message history for a Discord thread from the database."""
        # Use configured history limit? Or a different limit for threads?
        # Let's use max_channel_history for now, can be adjusted.
        effective_limit = limit if limit is not None else self.max_channel_history
        return self.db_manager.get_thread_history(str(thread_id), limit=effective_limit)

    def get_discord_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Gets thread data by Discord thread ID from the database."""
        return self.db_manager.get_thread_info(str(thread_id))

    def list_discord_threads_for_channel(self, channel_id: str) -> List[Dict[str, Any]]:
        """Lists all threads associated with a channel from the database."""
        return self.db_manager.list_threads_for_channel(str(channel_id))

    def delete_discord_thread(self, thread_id: str) -> bool:
        """Deletes a thread by its ID from the database."""
        return self.db_manager.delete_thread(str(thread_id))

    def rename_discord_thread(self, thread_id: str, new_name: str) -> bool:
        """Renames a thread in the database."""
        return self.db_manager.rename_thread(str(thread_id), new_name)

    def set_discord_thread_model(self, thread_id: str, model: Optional[str]):
        """Sets the specific model override for a thread in the database."""
        # Database call is synchronous
        self.db_manager.set_thread_model(str(thread_id), model)

    def set_discord_thread_system_prompt(self, thread_id: str, prompt: Optional[str]):
        """Sets the specific system prompt override for a thread in the database."""
        # Database call is synchronous
        self.db_manager.set_thread_system_prompt(str(thread_id), prompt)

    def get_discord_thread_config(self, thread_id: str) -> Optional[Dict[str, Optional[str]]]:
        """Gets model and system prompt for a thread from the database."""
        return self.db_manager.get_thread_config(str(thread_id))

    def get_thread_message_count(self, thread_id: str) -> int:
        """Gets the number of messages in a specific thread from the database."""
        return self.db_manager.get_thread_message_count(str(thread_id))


    # --- Pruning Method ---

    def prune_old_data(self) -> Dict[str, int]:
        """Prunes old messages, threads, sent reminders, and trivia sessions from the database."""
        logger.info("Starting data pruning...")
        message_cutoff = datetime.now() - timedelta(hours=self.time_window_hours)
        thread_cutoff = datetime.now() - timedelta(days=14)
        reminder_cutoff = datetime.now() - timedelta(days=30)
        trivia_session_days = 30  # Keep trivia sessions for 30 days

        try:
            messages_pruned = self.db_manager.prune_old_messages(message_cutoff)
            threads_pruned = self.db_manager.prune_old_threads(thread_cutoff)
            reminders_pruned = self.db_manager.prune_old_reminders(reminder_cutoff)
            trivia_sessions_pruned = self.db_manager.prune_old_trivia_sessions(trivia_session_days)

            prune_stats = {
                "messages_pruned": messages_pruned,
                "threads_pruned": threads_pruned,
                "reminders_pruned": reminders_pruned,
                "trivia_sessions_pruned": trivia_sessions_pruned,
                "channels_pruned": 0
            }
            logger.info(f"Pruning complete: {prune_stats}")
            return prune_stats
        except Exception as e:
            logger.error(f"Error during data pruning: {e}", exc_info=True)
            return {
                "messages_pruned": 0,
                "threads_pruned": 0,
                "reminders_pruned": 0,
                "trivia_sessions_pruned": 0,
                "channels_pruned": 0
            }


    # --- Model and System Prompt Methods ---

    def get_channel_system_prompt(self, channel_id: str) -> Optional[str]:
        """Gets the system prompt for a specific channel from the database."""
        return self.db_manager.get_channel_system_prompt(str(channel_id))

    def set_channel_system_prompt(self, channel_id: str, prompt: Optional[str]):
        """Sets a custom system prompt for a channel in the database."""
        # Database call is synchronous
        self.db_manager.set_channel_system_prompt(str(channel_id), prompt)

    def reset_channel_system_prompt(self, channel_id: str) -> bool:
        """Resets a channel to use the default system prompt in the database."""
        # Database call is synchronous
        return self.db_manager.reset_channel_config(str(channel_id)) # Resets both model and prompt

    def get_global_model(self) -> str:
        """Gets the current global model, ensuring provider/model format."""
        try:
            # Return cached value if available
            model = self.global_model
            # Ensure provider/model format. Add 'openrouter/' only if no separator exists.
            if "/" not in model and ":" not in model:
                 logger.warning(f"Global model '{model}' lacks provider prefix. Assuming 'openrouter'.")
                 model = f"openrouter/{model}"
            # Convert ':' to '/' if necessary (handle older format)
            elif ":" in model and "/" not in model:
                 logger.warning(f"Global model '{model}' uses ':' separator. Converting to '/'.")
                 model = model.replace(":", "/", 1)
            return model
        except AttributeError:
            # Fallback to DB if cache not initialized
            logger.warning("get_global_model called before state fully initialized. Fetching directly from DB.")
            model = self.db_manager.get_global_config(CONFIG_KEY_GLOBAL_MODEL, CONFIG_DEFAULT_MODEL)
            # Ensure provider/model format. Add 'openrouter/' only if no separator exists.
            if "/" not in model and ":" not in model:
                 logger.warning(f"DB Global model '{model}' lacks provider prefix. Assuming 'openrouter'.")
                 model = f"openrouter/{model}"
            # Convert ':' to '/' if necessary (handle older format)
            elif ":" in model and "/" not in model:
                 logger.warning(f"DB Global model '{model}' uses ':' separator. Converting to '/'.")
                 model = model.replace(":", "/", 1)
            return model

    async def set_global_model(self, model: str):
        """Sets the global model after validation (accepts provider:model or model format)."""
        if not self.model_manager:
            raise RuntimeError("ModelManager not set in BotStateManager")

        try:
            # Log the exact input string received by set_global_model
            logger.info(f"set_global_model received model string: '{model}'")
            # Parse and validate the model ID format
            provider, model_name = self.model_manager.parse_model_id(model) # 'model' is the input e.g., "openai/gpt-4-turbo"

            # Use the parsed provider and model_name to create the canonical ID in provider/model_name format
            canonical_model_id = f"{provider}/{model_name}"

            # Force refresh models for the parsed provider before validation
            await self.model_manager.get_models(provider, force_refresh=True)

            # Validate the canonical model ID (using the provider's list)
            is_valid = await self.model_manager.is_valid_model(canonical_model_id) # is_valid_model should handle provider/model format
            if not is_valid:
                # Fetch models for the specific provider for the error message
                provider_models = []
                try:
                    models = await self.model_manager.get_models(provider, force_refresh=False) # Use cache if possible
                    # Use slash separator for error message formatting
                    provider_models = [f"{provider}/{m}" for m in models]
                except Exception as ex:
                    logger.warning(f"Could not fetch models for provider {provider} for error message: {ex}")

                allowed_str = ', '.join(provider_models[:10]) + ('...' if len(provider_models) > 10 else '')
                # Use canonical_model_id in error message
                raise ValueError(f"Model '{canonical_model_id}' not found or is invalid for provider '{provider}'. Allowed for {provider}: {allowed_str}")

            # Store the validated, canonical model ID
            self.global_model = canonical_model_id
            # Save to DB (synchronous DB call)
            self.db_manager.set_global_config(CONFIG_KEY_GLOBAL_MODEL, canonical_model_id, 'string')
            logger.info(f"Global model set to: {canonical_model_id}")
        except ValueError as e:
            # Re-raise the ValueError with the original message
            raise ValueError(str(e))

    async def set_global_provider(self, provider: str):
        """Sets the global AI provider."""
        # Basic validation - could enhance later if needed
        if not isinstance(provider, str) or not provider:
            raise ValueError("Provider must be a non-empty string.")
        self.global_provider = provider
        await self._save_config(CONFIG_KEY_GLOBAL_PROVIDER, provider, 'string')
        logger.info(f"Global provider set to: {provider}")

    def get_global_system_prompt(self) -> Optional[str]:
        """Gets the global system prompt."""
        return self.global_system_prompt

    async def set_global_system_prompt(self, prompt: Optional[str]):
        """Sets the global system prompt."""
        self.global_system_prompt = prompt
        await self._save_config(CONFIG_KEY_GLOBAL_SYSTEM_PROMPT, prompt, 'string')
        logger.info(f"Global system prompt set to: {prompt[:50]}..." if prompt and len(prompt) > 50 else f"Global system prompt set to: {prompt}")

    async def set_channel_model(self, channel_id: str, model: Optional[str]):
        """Sets a channel-specific model after validation, storing in provider/model_name format."""
        canonical_model_id = None # Default to None if model input is None
        if model is not None: # Allow setting back to None to use global
            if not self.model_manager:
                raise RuntimeError("ProviderManager not set in BotStateManager")

            # Parse and create canonical ID *inside* the if block
            provider, model_name = self.model_manager.parse_model_id(model)
            canonical_model_id = f"{provider}/{model_name}"

            # Validate the canonical model ID (Correctly indented)
            is_valid = await self.model_manager.is_valid_model(canonical_model_id)
            if not is_valid:
                # Fetch models for the specific provider for the error message (Correctly indented)
                provider_models = []
                try:
                    models = await self.model_manager.get_models(provider, force_refresh=False) # Use cache if possible
                    provider_models = [f"{provider}/{m}" for m in models]
                except Exception as ex:
                    logger.warning(f"Could not fetch models for provider {provider} for error message: {ex}")

                allowed_str = ', '.join(provider_models[:10]) + ('...' if len(provider_models) > 10 else '')
                raise ValueError(f"Model '{canonical_model_id}' not found or is invalid for provider '{provider}'. Allowed for {provider}: {allowed_str}")

        # Save canonical ID (or None) to DB (synchronous DB call)
        self.db_manager.set_channel_model(str(channel_id), canonical_model_id)
        if canonical_model_id:
            logger.info(f"Channel {channel_id} model set to: {canonical_model_id}")
        else:
            logger.info(f"Channel {channel_id} model reset to global default.")

    async def set_channel_provider(self, channel_id: str, provider: str):
        """Sets the AI provider for a specific channel and refreshes models."""
        if not self.model_manager:
            raise RuntimeError("ModelManager not set in BotStateManager")
            
        providers = await self.model_manager.get_providers()
        if provider not in providers:
            raise ValueError(f"Invalid provider '{provider}'. Available: {', '.join(providers)}")
            
        # Force refresh models for the new provider
        if hasattr(self.model_manager, 'get_models') and callable(self.model_manager.get_models):
            # Handle both ProviderManager and ModelManager cases
            params = {}
            if 'force_refresh' in self.model_manager.get_models.__code__.co_varnames:
                params['force_refresh'] = True
            if 'provider' in self.model_manager.get_models.__code__.co_varnames:
                params['provider'] = provider
            await self.model_manager.get_models(**params)
            
        # Save to DB (synchronous DB call)
        self.db_manager.set_channel_provider(str(channel_id), provider)

    def get_channel_model(self, channel_id: str) -> Optional[str]:
        """Gets the channel-specific model override (returns None if using global)."""
        return self.db_manager.get_channel_model(str(channel_id))

    def get_channel_provider(self, channel_id: str) -> str:
        """Gets the AI provider for a specific channel."""
        provider = self.db_manager.get_channel_provider(str(channel_id))
        return provider if provider is not None else self.global_provider

    def get_global_provider(self) -> str:
        """Gets the global AI provider."""
        return self.global_provider

    def get_effective_model(self, channel_id: str) -> str:
        """Gets the effective model (persona > channel override > global default) in provider/model_name format."""
        logger.debug(f"[get_effective_model] Checking channel ID: {channel_id}")

        # Check persona model first
        persona = self.get_effective_persona(channel_id)
        if persona and persona.get('model'):
            logger.debug(f"[get_effective_model] Using persona model: {persona['model']}")
            model_to_return = persona['model']
            source = f"persona ({channel_id})"
        else:
            channel_model = self.db_manager.get_channel_model(str(channel_id))
            logger.debug(f"[get_effective_model] DB result for channel_model: {channel_model}")

            if channel_model is not None:
                model_to_return = channel_model
                source = f"channel override ({channel_id})"
                logger.debug(f"[get_effective_model] Using channel override: {model_to_return}")
            else:
                model_to_return = self.get_global_model()
                source = "global default"
                logger.debug(f"[get_effective_model] Using global default: {model_to_return}")

        logger.debug(f"[get_effective_model] Model before format check: {model_to_return} (Source: {source})")
        # Final check for format consistency (handle potential old data from channel config)
        if model_to_return and "/" not in model_to_return and ":" not in model_to_return:
             logger.warning(f"Effective model '{model_to_return}' from {source} lacks provider prefix. Assuming 'openrouter'.")
             model_to_return = f"openrouter/{model_to_return}"
        elif model_to_return and ":" in model_to_return and "/" not in model_to_return:
             logger.warning(f"Effective model '{model_to_return}' from {source} uses ':' separator. Converting to '/'.")
             model_to_return = model_to_return.replace(":", "/", 1)
        elif not model_to_return: # Should not happen if get_global_model has fallback
             logger.error(f"Effective model resolution failed for channel {channel_id}. Falling back to absolute default.")
             return CONFIG_DEFAULT_MODEL

        logger.debug(f"[get_effective_model] Final effective model for channel {channel_id}: {model_to_return} (from {source})")
        return model_to_return

    def get_all_channel_configs(self) -> List[Dict[str, Any]]:
        """Gets detailed configuration for all channels with overrides."""
        return self.db_manager.get_all_channel_configs()

    def get_all_thread_configs(self) -> List[Dict[str, Any]]:
        """Gets detailed configuration for all threads with overrides."""
        return self.db_manager.get_all_thread_configs()

    def reset_channel_config(self, channel_id: str) -> bool:
        """Resets channel configuration to use global defaults."""
        return self.db_manager.reset_channel_config(str(channel_id))

    # --- Persona Methods ---

    def get_channel_persona(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Gets the persona configuration for a channel, or None if not configured."""
        return self.db_manager.get_channel_persona(str(channel_id))

    def get_effective_persona(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Returns the active persona for a channel, or None if no active persona.

        If the persona is linked to a template, merges template values as fallbacks
        for any fields the channel persona hasn't explicitly set. This means edits
        to a template automatically propagate to all linked channel personas.
        """
        persona = self.db_manager.get_channel_persona(str(channel_id))
        if not persona or not persona.get('is_active'):
            return None

        # If linked to a template, merge template fields as fallbacks
        template_id = persona.get('template_id')
        if template_id:
            template = self.db_manager.get_persona_template(template_id)
            if template:
                mergeable = ('display_name', 'avatar_url', 'system_prompt',
                             'model', 'provider', 'response_style')
                for field in mergeable:
                    if not persona.get(field) and template.get(field):
                        persona[field] = template[field]

        return persona

    def get_effective_system_prompt(self, channel_id: str) -> Optional[str]:
        """Gets the effective system prompt: Persona > Channel Config > Global."""
        persona = self.get_effective_persona(channel_id)
        if persona and persona.get('system_prompt'):
            return persona['system_prompt']
        channel_prompt = self.get_channel_system_prompt(channel_id)
        if channel_prompt:
            return channel_prompt
        return self.get_global_system_prompt()

    def get_effective_provider(self, channel_id: str) -> str:
        """Gets the effective provider: Persona > Channel Config > Global."""
        persona = self.get_effective_persona(channel_id)
        if persona and persona.get('provider'):
            return persona['provider']
        return self.get_channel_provider(channel_id)

    def set_channel_persona(self, channel_id: str, display_name: str, **kwargs) -> bool:
        """Sets or updates the persona for a channel."""
        return self.db_manager.set_channel_persona(str(channel_id), display_name, **kwargs)

    def remove_channel_persona(self, channel_id: str) -> bool:
        """Removes the persona for a channel."""
        return self.db_manager.remove_channel_persona(str(channel_id))

    def toggle_channel_persona(self, channel_id: str) -> Optional[bool]:
        """Toggles persona active state. Returns new state or None if not found."""
        return self.db_manager.toggle_channel_persona(str(channel_id))

    def get_all_channel_personas(self) -> List[Dict[str, Any]]:
        """Gets all channel persona configurations."""
        return self.db_manager.get_all_channel_personas()

    def get_all_persona_templates(self) -> List[Dict[str, Any]]:
        """Gets all persona templates."""
        return self.db_manager.get_all_persona_templates()

    def get_persona_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Gets a persona template by ID."""
        return self.db_manager.get_persona_template(template_id)

    # --- News Feed Methods (Delegation) ---
    # COMMENTED OUT: News feeds feature removed
    # Methods preserved for potential future data export

    # def get_news_feeds(self) -> List[Dict[str, Any]]:
    #     return self.db_manager.get_news_feeds()

    # def add_news_feed(self, feed_id: str, url: str, name: Optional[str] = None, category: Optional[str] = None):
    #     """Adds or updates a news feed in the database, including URL and category."""
    #     # Pass all relevant info to the database manager method
    #     self.db_manager.add_news_feed(feed_id, url, name, category)

    # def delete_news_feed(self, feed_id: str) -> bool:
    #     return self.db_manager.delete_news_feed(feed_id)

    # def add_news_subscription(self, channel_id: str, feed_id: str):
    #     self.db_manager.add_news_subscription(str(channel_id), feed_id)

    # def remove_news_subscription(self, channel_id: str, feed_id: str) -> bool:
    #     return self.db_manager.remove_news_subscription(str(channel_id), feed_id)

    # def get_subscribed_channels(self, feed_id: str) -> List[str]:
    #     return self.db_manager.get_subscribed_channels(feed_id)

    # def get_channel_subscriptions(self, channel_id: str) -> List[str]:
    #     return self.db_manager.get_channel_subscriptions(str(channel_id))

    # def add_article_history(self, article_identifier: str, feed_id: str):
    #     self.db_manager.add_article_history(article_identifier, feed_id, datetime.now())

    # def check_article_history(self, article_identifier: str, feed_id: str) -> bool:
    #     return self.db_manager.check_article_history(article_identifier, feed_id)

    # def update_feed_last_checked(self, feed_id: str):
    #      # Ensure we store timezone-aware UTC timestamp
    #      from datetime import timezone
    #      self.db_manager.update_feed_last_checked(feed_id, datetime.now(timezone.utc))

    # def get_news_article_history_count(self) -> int:
    #     """Gets the total count of news article history records from the database."""
    #     return self.db_manager.get_news_article_history_count()

    # def set_last_digest_content(self, content: Optional[str]):
    #     """Stores the last generated news digest content in the database."""
    #     self.db_manager.set_last_digest_content(content)

    # def get_last_digest_content(self) -> Optional[str]:
    #     """Retrieves the last generated news digest content from the database."""
    #     return self.db_manager.get_last_digest_content()

    # # --- Article Summary Methods (Delegation) ---

    # def add_article_summary(self, article_id: str, feed_id: str, title: str, link: str,
    #                         published_date: Optional[datetime], summary_text: str,
    #                         feed_name: Optional[str], feed_category: Optional[str]):
    #     """Adds or replaces an article summary in the database."""
    #     # Pass data to the database manager method
    #     self.db_manager.add_article_summary(
    #         article_id=article_id,
    #         feed_id=feed_id,
    #         title=title,
    #         link=link,
    #         published_date=published_date,
    #         summary_text=summary_text,
    #         feed_name=feed_name,
    #         feed_category=feed_category,
    #         timestamp_summarized=datetime.now() # Add timestamp here
    #     )

    # def get_article_summaries(self, feed_ids: Optional[List[str]] = None,
    #                           category: Optional[str] = None,
    #                           limit: Optional[int] = 50) -> List[Dict[str, Any]]:
    #     """
    #     Retrieves recent article summaries from the database, optionally filtered.
    #     Uses the configured retention period to limit how far back it looks.
    #     """
    #     since_cutoff = datetime.now() - timedelta(days=self.summary_retention_days)
    #     return self.db_manager.get_article_summaries(
    #         feed_ids=feed_ids,
    #         category=category,
    #         since=since_cutoff,
    #         limit=limit
    #     )


    # # --- User-Specific Article Summary Methods (Delegation) ---

    # def add_user_article_summary(self, user_id: str, article_link: str, feed_url: str,
    #                              title: Optional[str], published_date: Optional[datetime],
    #                              summary_text: str):
    #     """Adds or replaces a user-specific article summary."""
    #     # Add timestamp here before delegating
    #     self.db_manager.add_user_article_summary(
    #         user_id=user_id,
    #         article_link=article_link,
    #         feed_url=feed_url,
    #         title=title,
    #         published_date=published_date,
    #         summary_text=summary_text,
    #         timestamp_summarized=datetime.now()
    #     )

    # def get_user_article_summaries(self, user_id: str, limit: Optional[int] = 50) -> List[Dict[str, Any]]:
    #     """Retrieves recent article summaries for a specific user."""
    #     # Use configured retention period
    #     since_cutoff = datetime.now() - timedelta(days=self.summary_retention_days)
    #     return self.db_manager.get_user_article_summaries(
    #         user_id=user_id,
    #         since=since_cutoff,
    #         limit=limit
    #     )

    # def get_users_with_personal_feeds(self) -> List[str]:
    #     """Gets user IDs who have configured personal feeds."""
    #     return self.db_manager.get_users_with_personal_feeds()


    # --- Statistics Methods (Example) ---

    def get_message_count(self) -> int:
        """Gets the total number of messages stored."""
        sql = "SELECT COUNT(*) FROM MESSAGES;"
        try:
            cursor = self.db_manager._get_cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
            return row[0] if row else 0
        except sqlite3.Error as e:
            logger.error(f"Error getting message count: {e}", exc_info=True)
            return -1 # Indicate error

    def get_thread_count(self) -> int:
        """Gets the total number of threads stored."""
        sql = "SELECT COUNT(*) FROM THREADS;"
        try:
            cursor = self.db_manager._get_cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
            return row[0] if row else 0
        except sqlite3.Error as e:
            logger.error(f"Error getting thread count: {e}", exc_info=True)
            return -1

    # --- Reminder Methods (Delegation) ---

    def add_reminder(self, user_id: str, channel_id: str, message: str,
                     due_timestamp: datetime) -> int:
        """Adds a reminder to the database."""
        return self.db_manager.add_reminder(
            user_id=str(user_id),
            channel_id=str(channel_id),
            message=message,
            due_timestamp=due_timestamp
        )

    def get_due_reminders(self, current_time: datetime) -> List[Dict[str, Any]]:
        """Gets reminders that are due."""
        return self.db_manager.get_due_reminders(current_time)

    def mark_reminder_sent(self, reminder_id: int) -> bool:
        """Marks a reminder as sent."""
        return self.db_manager.mark_reminder_sent(reminder_id)

    def get_user_reminders(self, user_id: str, include_sent: bool = False) -> List[Dict[str, Any]]:
        """Gets reminders for a specific user."""
        return self.db_manager.get_user_reminders(str(user_id), include_sent)

    def delete_reminder(self, reminder_id: int, user_id: str) -> bool:
        """Deletes a reminder by ID."""
        return self.db_manager.delete_reminder(reminder_id, str(user_id))

    # ===== Trivia Methods =====

    def create_trivia_session(self, thread_id: str, channel_id: str, user_id: Optional[str],
                             game_mode: str, category: Optional[str], difficulty: str,
                             questions_total: int = 10) -> int:
        """Creates a new trivia game session."""
        return self.db_manager.create_trivia_session(
            thread_id=str(thread_id),
            channel_id=str(channel_id),
            user_id=str(user_id) if user_id else None,
            game_mode=game_mode,
            category=category,
            difficulty=difficulty,
            questions_total=questions_total
        )

    def get_active_trivia_session(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Gets the active trivia session for a thread."""
        return self.db_manager.get_active_trivia_session(str(thread_id))

    def update_trivia_questions_answered(self, thread_id: str) -> bool:
        """Increments questions_answered counter for a trivia session."""
        return self.db_manager.update_trivia_questions_answered(str(thread_id))

    def end_trivia_session(self, thread_id: str) -> bool:
        """Ends a trivia session."""
        return self.db_manager.end_trivia_session(str(thread_id))

    def update_trivia_leaderboard(self, user_id: str, server_id: str,
                                  questions_answered: int, correct_answers: int,
                                  points_earned: int, current_streak: int,
                                  response_time: float) -> bool:
        """Updates trivia leaderboard stats for a user."""
        return self.db_manager.update_trivia_leaderboard(
            user_id=str(user_id),
            server_id=str(server_id),
            questions_answered=questions_answered,
            correct_answers=correct_answers,
            points_earned=points_earned,
            current_streak=current_streak,
            response_time=response_time
        )

    def get_trivia_leaderboard(self, server_id: str, timeframe: str = 'all_time',
                              limit: int = 10) -> List[Dict[str, Any]]:
        """Gets trivia leaderboard rankings for a server."""
        return self.db_manager.get_trivia_leaderboard(str(server_id), timeframe, limit)

    def get_trivia_user_stats(self, user_id: str, server_id: str) -> Optional[Dict[str, Any]]:
        """Gets trivia stats for a specific user."""
        return self.db_manager.get_trivia_user_stats(str(user_id), str(server_id))

    def add_trivia_achievement(self, user_id: str, server_id: str,
                              achievement_type: str, achievement_name: str,
                              metadata_json: Optional[str] = None) -> int:
        """Adds a trivia achievement for a user."""
        return self.db_manager.add_trivia_achievement(
            user_id=str(user_id),
            server_id=str(server_id),
            achievement_type=achievement_type,
            achievement_name=achievement_name,
            metadata_json=metadata_json
        )

    def get_trivia_user_achievements(self, user_id: str, server_id: str) -> List[Dict[str, Any]]:
        """Gets all trivia achievements for a user."""
        return self.db_manager.get_trivia_user_achievements(str(user_id), str(server_id))

    def has_trivia_achievement(self, user_id: str, server_id: str, achievement_type: str) -> bool:
        """Checks if user has a specific trivia achievement."""
        return self.db_manager.has_trivia_achievement(str(user_id), str(server_id), achievement_type)

    # def get_news_feeds_count(self) -> int:
    #     """Gets the count of configured news feeds."""
    #     # This could be slightly more efficient than fetching all feeds
    #     sql = "SELECT COUNT(*) FROM NEWS_FEEDS;"
    #     try:
    #         cursor = self.db_manager._get_cursor()
    #         cursor.execute(sql)
    #         row = cursor.fetchone()
    #         return row[0] if row else 0
    #     except sqlite3.Error as e:
    #         logger.error(f"Error getting news feed count: {e}", exc_info=True)
    #         return -1

    # def get_news_channel_config_count(self) -> int:
    #     """Gets the count of channel subscriptions."""
    #     sql = "SELECT COUNT(*) FROM NEWS_CHANNEL_SUBSCRIPTIONS;"
    #     try:
    #         cursor = self.db_manager._get_cursor()
    #         cursor.execute(sql)
    #         row = cursor.fetchone()
    #         return row[0] if row else 0
    #     except sqlite3.Error as e:
    #         logger.error(f"Error getting news subscription count: {e}", exc_info=True)
    #         return -1
