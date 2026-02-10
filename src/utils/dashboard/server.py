"""Dashboard web server for Gideon bot admin interface."""
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import List, Optional

from aiohttp import web, WSMsgType

from .auth import (
    auth_middleware,
    generate_session_token,
    validate_session_token,
    invalidate_session_token,
    verify_secret,
    cleanup_expired_sessions,
)

logger = logging.getLogger(__name__)


class DashboardServer:
    """Manages the aiohttp web server that serves the admin dashboard."""

    def __init__(self, bot, secret: str, port: int = 8080):
        self.bot = bot
        self.secret = secret
        self.port = port
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._ws_clients: List[web.WebSocketResponse] = []
        self._start_time = time.time()

    async def start(self):
        """Start the dashboard web server."""
        self.app = web.Application(middlewares=[auth_middleware])
        self._register_routes()
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        logger.info(f"Dashboard server started on port {self.port}")

    async def stop(self):
        """Stop the dashboard web server."""
        # Close all WebSocket connections
        for ws in list(self._ws_clients):
            await ws.close()
        self._ws_clients.clear()

        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("Dashboard server stopped")

    def _register_routes(self):
        """Register all HTTP and WebSocket routes."""
        router = self.app.router

        # Static files (dashboard frontend)
        dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'dashboard')
        css_dir = os.path.join(dashboard_dir, 'css')
        js_dir = os.path.join(dashboard_dir, 'js')

        # Page routes
        router.add_get('/', self._handle_index)
        router.add_get('/login', self._handle_login_page)

        # Static asset routes
        if os.path.isdir(css_dir):
            router.add_static('/css/', css_dir)
        if os.path.isdir(js_dir):
            router.add_static('/js/', js_dir)

        # Auth API
        router.add_post('/api/auth/login', self._handle_login)
        router.add_post('/api/auth/logout', self._handle_logout)
        router.add_get('/api/auth/check', self._handle_auth_check)

        # Overview API
        router.add_get('/api/overview', self._handle_overview)

        # Settings API
        router.add_get('/api/settings', self._handle_get_settings)
        router.add_put('/api/settings', self._handle_update_settings)

        # Intent settings API
        router.add_get('/api/settings/intent', self._handle_get_intent_settings)
        router.add_put('/api/settings/intent', self._handle_update_intent_settings)

        # Channel API
        router.add_get('/api/channels', self._handle_get_channels)
        router.add_get('/api/channels/{channel_id}', self._handle_get_channel)
        router.add_put('/api/channels/{channel_id}', self._handle_update_channel)
        router.add_delete('/api/channels/{channel_id}', self._handle_reset_channel)

        # Thread API
        router.add_get('/api/threads', self._handle_get_threads)
        router.add_get('/api/threads/{thread_id}', self._handle_get_thread)
        router.add_put('/api/threads/{thread_id}', self._handle_update_thread)
        router.add_delete('/api/threads/{thread_id}', self._handle_delete_thread)

        # Models API
        router.add_get('/api/models/{provider}', self._handle_get_models)
        router.add_get('/api/providers', self._handle_get_providers)

        # Diagnostics API
        router.add_get('/api/diagnostics', self._handle_diagnostics)
        router.add_post('/api/diagnostics/prune', self._handle_prune)

        # WebSocket for real-time updates
        router.add_get('/ws', self._handle_websocket)

    # ── Page Handlers ──────────────────────────────────────────────

    async def _handle_index(self, request):
        """Serve the main dashboard page."""
        dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'dashboard')
        index_path = os.path.join(dashboard_dir, 'index.html')
        if os.path.exists(index_path):
            return web.FileResponse(index_path)
        return web.Response(text='Dashboard files not found', status=404)

    async def _handle_login_page(self, request):
        """Serve the login page (same index.html, JS handles routing)."""
        return await self._handle_index(request)

    # ── Auth Handlers ──────────────────────────────────────────────

    async def _handle_login(self, request):
        """Handle login with secret key."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        provided_secret = data.get('secret', '')
        if not verify_secret(provided_secret, self.secret):
            logger.warning(f"Failed login attempt from {request.remote}")
            return web.json_response({'error': 'Invalid secret'}, status=401)

        token = generate_session_token(self.secret)
        response = web.json_response({'status': 'ok', 'token': token})
        response.set_cookie('session_token', token, max_age=86400, httponly=True, samesite='Strict')
        logger.info(f"Successful login from {request.remote}")
        return response

    async def _handle_logout(self, request):
        """Handle logout."""
        token = request.cookies.get('session_token')
        if token:
            invalidate_session_token(token)
        response = web.json_response({'status': 'ok'})
        response.del_cookie('session_token')
        return response

    async def _handle_auth_check(self, request):
        """Check if the current session is valid. Returns the token so JS can use it for WebSocket."""
        token = request.cookies.get('session_token')
        if not token:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]

        if token and validate_session_token(token):
            return web.json_response({'authenticated': True, 'token': token})
        return web.json_response({'authenticated': False})

    # ── Overview Handler ───────────────────────────────────────────

    async def _handle_overview(self, request):
        """Get dashboard overview data."""
        state = self.bot.state_manager
        uptime_seconds = int(time.time() - self._start_time)

        # Gather stats
        message_count = state.get_message_count()
        thread_count = state.get_thread_count()
        channel_configs = state.get_all_channel_configs()
        guild_count = len(self.bot.guilds) if hasattr(self.bot, 'guilds') else 0

        # Database file info
        db_path = state.db_manager.db_path
        db_size = 0
        if os.path.exists(db_path):
            db_size = os.path.getsize(db_path)

        return web.json_response({
            'bot_name': str(self.bot.user) if self.bot.user else 'Unknown',
            'bot_id': str(self.bot.user.id) if self.bot.user else 'Unknown',
            'guilds': guild_count,
            'uptime_seconds': uptime_seconds,
            'message_count': message_count,
            'thread_count': thread_count,
            'channel_config_count': len(channel_configs),
            'database_size_bytes': db_size,
            'global_model': state.get_global_model(),
            'global_provider': state.get_global_provider(),
            'latency_ms': round(self.bot.latency * 1000, 1) if hasattr(self.bot, 'latency') else None,
        })

    # ── Settings Handlers ──────────────────────────────────────────

    async def _handle_get_settings(self, request):
        """Get all global settings."""
        state = self.bot.state_manager
        return web.json_response({
            'global_model': state.get_global_model(),
            'global_provider': state.get_global_provider(),
            'global_system_prompt': state.get_global_system_prompt(),
            'max_channel_history': state.get_max_channel_history(),
            'time_window_hours': state.get_time_window_hours(),
            'prune_frequency_hours': state.get_prune_frequency_hours(),
        })

    async def _handle_update_settings(self, request):
        """Update global settings."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        state = self.bot.state_manager
        updated = []

        try:
            if 'global_model' in data:
                await state.set_global_model(data['global_model'])
                updated.append('global_model')

            if 'global_provider' in data:
                await state.set_global_provider(data['global_provider'])
                updated.append('global_provider')

            if 'global_system_prompt' in data:
                await state.set_global_system_prompt(data['global_system_prompt'])
                updated.append('global_system_prompt')

            if 'max_channel_history' in data:
                val = int(data['max_channel_history'])
                if val < 1 or val > 100:
                    return web.json_response({'error': 'max_channel_history must be 1-100'}, status=400)
                await state.set_max_channel_history(val)
                updated.append('max_channel_history')

            if 'time_window_hours' in data:
                val = int(data['time_window_hours'])
                if val < 1 or val > 96:
                    return web.json_response({'error': 'time_window_hours must be 1-96'}, status=400)
                await state.set_time_window_hours(val)
                updated.append('time_window_hours')

            if 'prune_frequency_hours' in data:
                val = int(data['prune_frequency_hours'])
                await state.set_prune_frequency_hours(val)
                updated.append('prune_frequency_hours')

        except ValueError as e:
            return web.json_response({'error': str(e)}, status=400)

        await self._broadcast_ws({'type': 'settings_updated', 'fields': updated})
        return web.json_response({'status': 'ok', 'updated': updated})

    async def _handle_get_intent_settings(self, request):
        """Get intent detection settings."""
        state = self.bot.state_manager
        return web.json_response({
            'enabled': state.get_intent_enabled(),
            'model': state.get_intent_model(),
            'threshold': state.get_intent_threshold(),
        })

    async def _handle_update_intent_settings(self, request):
        """Update intent detection settings."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        state = self.bot.state_manager
        updated = []

        try:
            if 'enabled' in data:
                await state.set_intent_enabled(bool(data['enabled']))
                updated.append('enabled')

            if 'model' in data:
                await state.set_intent_model(data['model'])
                updated.append('model')

            if 'threshold' in data:
                await state.set_intent_threshold(float(data['threshold']))
                updated.append('threshold')

        except ValueError as e:
            return web.json_response({'error': str(e)}, status=400)

        await self._broadcast_ws({'type': 'intent_settings_updated', 'fields': updated})
        return web.json_response({'status': 'ok', 'updated': updated})

    # ── Channel Handlers ───────────────────────────────────────────

    async def _handle_get_channels(self, request):
        """Get all channels with custom configurations."""
        state = self.bot.state_manager
        configs = state.get_all_channel_configs()

        # Enrich with Discord channel names if available
        enriched = []
        for cfg in configs:
            channel_id = cfg.get('channel_id', '')
            channel_name = None
            guild_name = None
            try:
                ch = self.bot.get_channel(int(channel_id))
                if ch:
                    channel_name = ch.name
                    if hasattr(ch, 'guild') and ch.guild:
                        guild_name = ch.guild.name
            except (ValueError, AttributeError):
                pass

            enriched.append({
                **cfg,
                'channel_name': channel_name,
                'guild_name': guild_name,
            })

        return web.json_response(enriched)

    async def _handle_get_channel(self, request):
        """Get configuration for a specific channel."""
        channel_id = request.match_info['channel_id']
        state = self.bot.state_manager

        model = state.get_channel_model(channel_id)
        provider = state.get_channel_provider(channel_id)
        system_prompt = state.get_channel_system_prompt(channel_id)
        effective_model = state.get_effective_model(channel_id)

        channel_name = None
        try:
            ch = self.bot.get_channel(int(channel_id))
            if ch:
                channel_name = ch.name
        except (ValueError, AttributeError):
            pass

        return web.json_response({
            'channel_id': channel_id,
            'channel_name': channel_name,
            'model': model,
            'provider': provider,
            'system_prompt': system_prompt,
            'effective_model': effective_model,
        })

    async def _handle_update_channel(self, request):
        """Update channel configuration."""
        channel_id = request.match_info['channel_id']
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        state = self.bot.state_manager
        updated = []

        try:
            if 'model' in data:
                await state.set_channel_model(channel_id, data['model'] or None)
                updated.append('model')

            if 'provider' in data:
                await state.set_channel_provider(channel_id, data['provider'])
                updated.append('provider')

            if 'system_prompt' in data:
                state.set_channel_system_prompt(channel_id, data['system_prompt'] or None)
                updated.append('system_prompt')

        except ValueError as e:
            return web.json_response({'error': str(e)}, status=400)

        await self._broadcast_ws({'type': 'channel_updated', 'channel_id': channel_id, 'fields': updated})
        return web.json_response({'status': 'ok', 'updated': updated})

    async def _handle_reset_channel(self, request):
        """Reset channel to global defaults."""
        channel_id = request.match_info['channel_id']
        state = self.bot.state_manager
        result = state.reset_channel_config(channel_id)

        await self._broadcast_ws({'type': 'channel_reset', 'channel_id': channel_id})
        return web.json_response({'status': 'ok', 'reset': result})

    # ── Thread Handlers ────────────────────────────────────────────

    async def _handle_get_threads(self, request):
        """Get all threads."""
        state = self.bot.state_manager
        # Get threads from all channels with configs
        all_threads = []

        # Query all threads from the database directly
        try:
            cursor = state.db_manager._get_cursor()
            cursor.execute("SELECT thread_id, channel_id, name, created_at, model, system_prompt FROM THREADS ORDER BY created_at DESC")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            for row in rows:
                thread_data = dict(zip(columns, row))
                # Add message count
                thread_data['message_count'] = state.get_thread_message_count(thread_data['thread_id'])
                all_threads.append(thread_data)
        except Exception as e:
            logger.error(f"Error fetching threads: {e}", exc_info=True)

        return web.json_response(all_threads)

    async def _handle_get_thread(self, request):
        """Get a specific thread's details."""
        thread_id = request.match_info['thread_id']
        state = self.bot.state_manager

        thread_info = state.get_discord_thread(thread_id)
        if not thread_info:
            return web.json_response({'error': 'Thread not found'}, status=404)

        thread_config = state.get_discord_thread_config(thread_id)
        message_count = state.get_thread_message_count(thread_id)

        result = {
            **thread_info,
            'message_count': message_count,
        }
        if thread_config:
            result['model'] = thread_config.get('model')
            result['system_prompt'] = thread_config.get('system_prompt')

        return web.json_response(result)

    async def _handle_update_thread(self, request):
        """Update thread configuration."""
        thread_id = request.match_info['thread_id']
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON'}, status=400)

        state = self.bot.state_manager
        updated = []

        if 'name' in data:
            state.rename_discord_thread(thread_id, data['name'])
            updated.append('name')

        if 'model' in data:
            state.set_discord_thread_model(thread_id, data['model'] or None)
            updated.append('model')

        if 'system_prompt' in data:
            state.set_discord_thread_system_prompt(thread_id, data['system_prompt'] or None)
            updated.append('system_prompt')

        await self._broadcast_ws({'type': 'thread_updated', 'thread_id': thread_id, 'fields': updated})
        return web.json_response({'status': 'ok', 'updated': updated})

    async def _handle_delete_thread(self, request):
        """Delete a thread."""
        thread_id = request.match_info['thread_id']
        state = self.bot.state_manager
        result = state.delete_discord_thread(thread_id)

        await self._broadcast_ws({'type': 'thread_deleted', 'thread_id': thread_id})
        return web.json_response({'status': 'ok', 'deleted': result})

    # ── Models Handlers ─────────────────────────────────────────────

    async def _handle_get_providers(self, request):
        """Get list of available AI providers."""
        providers = []
        if self.bot.openrouter_client:
            providers.append('openrouter')
        if self.bot.openai_client:
            providers.append('openai')
        return web.json_response(providers)

    async def _handle_get_models(self, request):
        """Get available models for a specific provider."""
        provider = request.match_info['provider']
        try:
            model_ids = await self.bot.model_manager.get_models(provider)
            # Format as provider/model_id (matching slash command behavior)
            formatted = [f"{provider}/{mid}" for mid in model_ids]
            return web.json_response(formatted)
        except ValueError as e:
            return web.json_response({'error': str(e)}, status=400)
        except Exception as e:
            logger.error(f"Error fetching models for {provider}: {e}", exc_info=True)
            return web.json_response({'error': f'Failed to fetch models: {str(e)}'}, status=500)

    # ── Diagnostics Handlers ───────────────────────────────────────

    async def _handle_diagnostics(self, request):
        """Run diagnostics and return results."""
        state = self.bot.state_manager
        results = {
            'timestamp': datetime.now().isoformat(),
            'bot_status': 'online' if self.bot.is_ready() else 'starting',
            'latency_ms': round(self.bot.latency * 1000, 1) if hasattr(self.bot, 'latency') else None,
            'guilds': len(self.bot.guilds) if hasattr(self.bot, 'guilds') else 0,
            'uptime_seconds': int(time.time() - self._start_time),
        }

        # Database check
        try:
            msg_count = state.get_message_count()
            thread_count = state.get_thread_count()
            db_path = state.db_manager.db_path
            results['database'] = {
                'status': 'ok' if msg_count >= 0 else 'error',
                'message_count': msg_count,
                'thread_count': thread_count,
                'file_size_bytes': os.path.getsize(db_path) if os.path.exists(db_path) else 0,
            }
        except Exception as e:
            results['database'] = {'status': 'error', 'error': str(e)}

        # Provider checks
        providers = {}
        if self.bot.openrouter_client:
            try:
                models = await self.bot.model_manager.get_models('openrouter')
                providers['openrouter'] = {'status': 'ok', 'model_count': len(models)}
            except Exception as e:
                providers['openrouter'] = {'status': 'error', 'error': str(e)}

        if self.bot.openai_client:
            try:
                models = await self.bot.model_manager.get_models('openai')
                providers['openai'] = {'status': 'ok', 'model_count': len(models)}
            except Exception as e:
                providers['openai'] = {'status': 'error', 'error': str(e)}

        if self.bot.ai_horde_client:
            providers['ai_horde'] = {'status': 'configured'}

        results['providers'] = providers

        # Settings summary
        results['settings'] = {
            'global_model': state.get_global_model(),
            'global_provider': state.get_global_provider(),
            'max_channel_history': state.get_max_channel_history(),
            'time_window_hours': state.get_time_window_hours(),
            'prune_frequency_hours': state.get_prune_frequency_hours(),
            'intent_enabled': state.get_intent_enabled(),
        }

        return web.json_response(results)

    async def _handle_prune(self, request):
        """Trigger manual data pruning."""
        state = self.bot.state_manager
        try:
            stats = state.prune_old_data()
            await self._broadcast_ws({'type': 'prune_completed', 'stats': stats})
            return web.json_response({'status': 'ok', 'stats': stats})
        except Exception as e:
            logger.error(f"Error during manual prune: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)

    # ── WebSocket Handler ──────────────────────────────────────────

    async def _handle_websocket(self, request):
        """Handle WebSocket connections for real-time updates."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Authenticate the WebSocket connection
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=10.0)
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                token = data.get('token', '')
                if not validate_session_token(token):
                    await ws.send_json({'type': 'error', 'message': 'Unauthorized'})
                    await ws.close()
                    return ws
            else:
                await ws.close()
                return ws
        except (asyncio.TimeoutError, json.JSONDecodeError):
            await ws.close()
            return ws

        # Authenticated - add to clients
        self._ws_clients.append(ws)
        await ws.send_json({'type': 'connected', 'message': 'WebSocket connected'})
        logger.info(f"WebSocket client connected (total: {len(self._ws_clients)})")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if data.get('type') == 'ping':
                            await ws.send_json({'type': 'pong'})
                    except json.JSONDecodeError:
                        pass
                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)
            logger.info(f"WebSocket client disconnected (total: {len(self._ws_clients)})")

        return ws

    async def _broadcast_ws(self, data: dict):
        """Broadcast a message to all connected WebSocket clients."""
        if not self._ws_clients:
            return

        data['timestamp'] = datetime.now().isoformat()
        dead = []
        for ws in self._ws_clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._ws_clients.remove(ws)

    async def broadcast_event(self, event_type: str, data: dict = None):
        """Public method for cogs to broadcast events to dashboard clients."""
        payload = {'type': event_type}
        if data:
            payload.update(data)
        await self._broadcast_ws(payload)
