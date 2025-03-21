"""Persistence utilities for saving and loading bot state."""
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from ..config import DATA_DIRECTORY

logger = logging.getLogger("persistence")

class StatePersistence:
    """Handles saving and loading bot state to disk."""
    
    def __init__(self):
        """Initialize persistence with configured data directory."""
        self.data_dir = DATA_DIRECTORY
        self.state_file = os.path.join(self.data_dir, "state.json")
        self.backup_dir = os.path.join(self.data_dir, "backups")
        
        # Ensure directories exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Ensure state file exists
        self.ensure_state_file_exists()
        
        logger.info(f"Using state file: {self.state_file}")
        
    def ensure_state_file_exists(self):
        """Create a default empty state file if it doesn't exist."""
        if not os.path.exists(self.state_file):
            logger.info(f"Creating new empty state file at {self.state_file}")
            default_state = {
                "version": 1,
                "saved_at": datetime.now().isoformat(),
                "channel_history": {},
                "channel_models": {},
                "channel_system_prompts": {},
                "threads": {},
                "simple_id_mapping": {},
                "discord_threads": {},
                "max_channel_history": 35,
                "max_threads_per_channel": 10,
                "time_window_hours": 48,
                "global_model": ""  # Will be replaced with actual default on load
            }
            
            try:
                with open(self.state_file, 'w') as f:
                    json.dump(default_state, f, indent=2, default=self._serialize_datetime)
                logger.info("Empty state file created successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to create empty state file: {str(e)}")
                return False
        else:
            # File exists, check if it's valid JSON
            try:
                with open(self.state_file, 'r') as f:
                    json.load(f)
                logger.info(f"Using existing state file: {self.state_file}")
                return True
            except json.JSONDecodeError:
                logger.error(f"Existing state file contains invalid JSON, creating backup and new file")
                # Create a backup of the corrupt file
                corrupt_backup = f"{self.state_file}.corrupt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                try:
                    os.rename(self.state_file, corrupt_backup)
                    logger.info(f"Backed up corrupt file to {corrupt_backup}")
                    return self.ensure_state_file_exists()  # Recursively call to create a new file
                except Exception as e:
                    logger.error(f"Failed to backup corrupt state file: {str(e)}")
                    return False
        return True
        
    def _serialize_datetime(self, obj):
        """Custom JSON serializer to handle datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")
    
    def _deserialize_datetime(self, data):
        """Convert ISO datetime strings back to datetime objects."""
        for key, value in data.items():
            if isinstance(value, str) and len(value) > 10:
                try:
                    if 'T' in value and ('+' in value or 'Z' in value or '-' in value[10:]):
                        data[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    pass
            elif isinstance(value, dict):
                self._deserialize_datetime(value)
        return data
    
    def create_backup(self):
        """Create a backup of the current state file."""
        if not os.path.exists(self.state_file):
            logger.warning(f"Cannot backup - state file doesn't exist: {self.state_file}")
            return
            
        # Ensure backup directory exists
        os.makedirs(self.backup_dir, exist_ok=True)
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.backup_dir, f"state_{timestamp}.json")
        
        try:
            # Read from source file
            with open(self.state_file, 'r') as src:
                content = src.read()
            
            # Write to backup file
            with open(backup_file, 'w') as dst:
                dst.write(content)
                
            file_size = os.path.getsize(backup_file) / 1024
            logger.info(f"Created backup: {backup_file} ({file_size:.2f} KB)")
            
            # Clean up old backups (keep 10 most recent)
            backups = sorted([f for f in os.listdir(self.backup_dir) 
                             if f.startswith('state_') and f.endswith('.json')])
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    old_path = os.path.join(self.backup_dir, old_backup)
                    os.remove(old_path)
                logger.info(f"Removed {len(backups) - 10} old backups")
                
            return backup_file
        except FileNotFoundError as e:
            logger.error(f"File not found when creating backup: {str(e)}")
        except PermissionError as e:
            logger.error(f"Permission error when creating backup: {str(e)}")
        except IOError as e:
            logger.error(f"I/O error when creating backup: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to create backup: {str(e)}")
        
        return None
    
    def save_state(self, state_manager) -> bool:
        """Save the current state to disk."""
        try:
            # Create a backup of the existing state file
            self.create_backup()
            
            # Extract the relevant data from state manager
            state_data = {
                "version": 1,  # For future schema migrations
                "saved_at": datetime.now().isoformat(),
                
                # Conversation memory
                "channel_history": state_manager.channel_history,
                "channel_models": state_manager.channel_models,
                "channel_system_prompts": state_manager.channel_system_prompts,
                
                # Thread data
                "threads": state_manager.threads,
                "simple_id_mapping": state_manager.simple_id_mapping,
                "discord_threads": state_manager.discord_threads,
                
                # Configuration
                "max_channel_history": state_manager.max_channel_history,
                "max_threads_per_channel": state_manager.max_threads_per_channel,
                "time_window_hours": state_manager.time_window_hours,
                "global_model": state_manager.global_model
            }
            
            # Write to file with pretty formatting
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2, default=self._serialize_datetime)
            
            logger.info(f"State saved to {self.state_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {str(e)}")
            return False
    
    def load_state(self, state_manager) -> bool:
        """Load state from disk into the state manager."""
        try:
            if not os.path.exists(self.state_file):
                logger.info(f"No state file found at {self.state_file}")
                return False
            
            file_size = os.path.getsize(self.state_file)
            logger.info(f"Loading state file: {self.state_file} ({file_size/1024:.2f} KB)")
            
            with open(self.state_file, 'r') as f:
                state_data = json.load(f)
            
            # Process all timestamps
            self._process_nested_datetime(state_data)
            
            # Validate and update state manager with loaded data
            state_manager.channel_history = state_data.get("channel_history", {})
            state_manager.channel_models = state_data.get("channel_models", {})
            state_manager.channel_system_prompts = state_data.get("channel_system_prompts", {})
            state_manager.threads = state_data.get("threads", {})
            state_manager.simple_id_mapping = state_data.get("simple_id_mapping", {})
            state_manager.discord_threads = state_data.get("discord_threads", {})
            
            # Configuration values
            state_manager.max_channel_history = state_data.get("max_channel_history", 35)
            state_manager.max_threads_per_channel = state_data.get("max_threads_per_channel", 10)
            state_manager.time_window_hours = state_data.get("time_window_hours", 48)
            state_manager.global_model = state_data.get("global_model", state_manager.global_model)
            
            # Log metrics from loaded state
            channels = len(state_manager.channel_history)
            threads = sum(len(threads) for threads in state_manager.threads.values())
            messages = sum(len(msgs) for msgs in state_manager.channel_history.values())
            
            logger.info(f"State loaded: {channels} channels, {threads} threads, {messages} messages")
            return True
        except json.JSONDecodeError:
            logger.error(f"Failed to parse state file: invalid JSON")
            return False
        except Exception as e:
            logger.error(f"Failed to load state: {str(e)}")
            return False
    
    def _process_nested_datetime(self, data):
        """Process nested dictionaries and lists to convert datetime strings."""
        if isinstance(data, dict):
            # Process dictionary items
            for key, value in list(data.items()):
                if isinstance(value, str) and len(value) > 10:
                    try:
                        # Look for ISO format datetime strings
                        if 'T' in value and value.count('-') >= 2:
                            # Replace Z with +00:00 for ISO format compatibility
                            iso_value = value.replace('Z', '+00:00')
                            try:
                                data[key] = datetime.fromisoformat(iso_value)
                            except ValueError:
                                logger.debug(f"Could not convert to datetime: {value}")
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Error converting datetime: {e}")
                elif isinstance(value, dict):
                    self._process_nested_datetime(value)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            self._process_nested_datetime(item)
                        elif isinstance(item, str) and len(item) > 10:
                            try:
                                if 'T' in item and item.count('-') >= 2:
                                    iso_item = item.replace('Z', '+00:00')
                                    try:
                                        value[i] = datetime.fromisoformat(iso_item)
                                    except ValueError:
                                        pass
                            except (ValueError, TypeError):
                                pass
        elif isinstance(data, list):
            # Process list items recursively
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    self._process_nested_datetime(item)
        return data
