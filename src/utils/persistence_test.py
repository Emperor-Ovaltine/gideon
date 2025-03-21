"""Test script to verify the persistence system is working correctly."""
import os
import sys
import json
from datetime import datetime, timedelta

# Add the parent directory to sys.path to allow importing from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.utils.persistence import StatePersistence
from src.utils.state_manager import BotStateManager

def test_persistence():
    """Test saving and loading state."""
    # Create a clean test environment
    test_dir = "./test_data"
    os.makedirs(test_dir, exist_ok=True)
    
    # Create persistence handler
    persistence = StatePersistence(save_path=test_dir)
    
    # Get state manager instance
    state = BotStateManager()
    
    # Add some test data
    # 1. Channel history
    state.channel_history = {
        "123456789": [
            {
                "role": "user",
                "content": "Hello, bot!",
                "timestamp": datetime.now() - timedelta(minutes=5)
            },
            {
                "role": "assistant",
                "content": "Hello! How can I help you today?",
                "timestamp": datetime.now() - timedelta(minutes=4)
            }
        ]
    }
    
    # 2. Thread data
    state.threads = {
        "123456789": {
            "thread_1": {
                "name": "Test Thread",
                "created_at": datetime.now() - timedelta(hours=1),
                "messages": [
                    {
                        "role": "user",
                        "content": "This is a thread message",
                        "timestamp": datetime.now() - timedelta(minutes=30)
                    }
                ]
            }
        }
    }
    
    # 3. Configuration
    state.channel_models = {"123456789": "gpt-4"}
    state.channel_system_prompts = {"123456789": "You are a helpful assistant."}
    state.global_model = "gpt-3.5-turbo"
    
    # Save state
    print("Saving state...")
    result = persistence.save_state(state)
    print(f"Save result: {result}")
    
    # Verify the file exists
    state_file = os.path.join(test_dir, "state.json")
    if os.path.exists(state_file):
        print(f"State file created: {state_file} ({os.path.getsize(state_file)/1024:.2f} KB)")
        
        # Read the file content for inspection
        with open(state_file, 'r') as f:
            raw_data = json.load(f)
        print(f"Version: {raw_data.get('version')}")
        print(f"Saved at: {raw_data.get('saved_at')}")
        print(f"Channels: {len(raw_data.get('channel_history', {}))}")
    else:
        print("ERROR: State file was not created!")
        return
    
    # Create a new state manager to test loading
    print("\nTesting load functionality...")
    new_state = BotStateManager()
    # Clear the existing data
    new_state.channel_history = {}
    new_state.threads = {}
    
    # Load state
    load_result = persistence.load_state(new_state)
    print(f"Load result: {load_result}")
    
    # Verify data was loaded correctly
    print(f"Loaded channels: {len(new_state.channel_history)}")
    print(f"Loaded threads: {sum(len(threads) for threads in new_state.threads.values())}")
    print(f"Loaded global model: {new_state.global_model}")
    
    # Test datetime deserialization
    if "123456789" in new_state.channel_history:
        sample_message = new_state.channel_history["123456789"][0]
        print(f"Sample message timestamp type: {type(sample_message.get('timestamp'))}")
        if isinstance(sample_message.get('timestamp'), datetime):
            print("✅ Datetime deserialization successful")
        else:
            print("❌ Datetime deserialization failed")
    
    # Test datetime deserialization more thoroughly
    if "123456789" in new_state.channel_history:
        # Check channel history timestamps
        sample_message = new_state.channel_history["123456789"][0]
        print(f"Sample message timestamp type: {type(sample_message.get('timestamp'))}")
        if isinstance(sample_message.get('timestamp'), datetime):
            print("✅ Channel history datetime deserialization successful")
        else:
            print(f"❌ Channel history datetime deserialization failed: {sample_message.get('timestamp')}")
            
        # Check thread timestamps
        if "123456789" in new_state.threads and "thread_1" in new_state.threads["123456789"]:
            thread = new_state.threads["123456789"]["thread_1"]
            
            # Check created_at
            thread_created = thread.get("created_at")
            print(f"Thread created_at type: {type(thread_created)}")
            if isinstance(thread_created, datetime):
                print("✅ Thread created_at datetime deserialization successful")
            else:
                print(f"❌ Thread created_at datetime deserialization failed: {thread_created}")
                
            # Check thread messages
            if thread.get("messages") and len(thread["messages"]) > 0:
                thread_msg = thread["messages"][0]
                thread_timestamp = thread_msg.get("timestamp")
                print(f"Thread message timestamp type: {type(thread_timestamp)}")
                if isinstance(thread_timestamp, datetime):
                    print("✅ Thread message datetime deserialization successful")
                else:
                    print(f"❌ Thread message datetime deserialization failed: {thread_timestamp}")
    
    # Dump some sample data to help debug
    print("\nSample of loaded data:")
    if "123456789" in new_state.channel_history and new_state.channel_history["123456789"]:
        sample = new_state.channel_history["123456789"][0]
        print(f"Channel history first message: {sample}")
    
    # Clean up test files if everything worked
    if result and load_result:
        print("\nTests passed - cleaning up test files...")
        os.remove(state_file)
        os.rmdir(os.path.join(test_dir, "backups"))
        os.rmdir(test_dir)
        print("Test files cleaned up")
    
    return result and load_result

if __name__ == "__main__":
    print("=== Testing Persistence System ===")
    success = test_persistence()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")
    sys.exit(0 if success else 1)
