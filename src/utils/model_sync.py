"""Utilities for synchronizing model state between cogs."""
import logging

logger = logging.getLogger('model_sync')

def sync_models(bot):
    """Synchronize model settings across all cogs.
    
    This ensures that all OpenRouterClient instances use the same model.
    """
    logger.info("Synchronizing model settings across cogs...")
    
    # Get the state manager
    state_manager = None
    for cog_name, cog in bot.cogs.items():
        if hasattr(cog, 'state'):
            state_manager = cog.state
            break
    
    if not state_manager:
        logger.error("Could not find state manager in any cog")
        return
    
    # Get the global model
    global_model = state_manager.get_global_model()
    logger.info(f"Global model is: {global_model}")
    
    # Update model in all cogs
    for cog_name, cog in bot.cogs.items():
        if hasattr(cog, 'openrouter_client'):
            logger.info(f"Setting model for {cog_name} to {global_model}")
            cog.openrouter_client.model = global_model
    
    logger.info("Model synchronization complete")
