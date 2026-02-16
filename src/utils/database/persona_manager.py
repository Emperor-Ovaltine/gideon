import sqlite3
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class PersonaManager:
    """Manages persona templates and per-channel persona configuration."""

    def __init__(self, conn):
        self._conn = conn

    # --- Persona Templates ---

    def add_persona_template(self, template_id: str, name: str, display_name: str,
                             avatar_url: Optional[str] = None, system_prompt: Optional[str] = None,
                             model: Optional[str] = None, provider: Optional[str] = None,
                             response_style: Optional[str] = None, description: Optional[str] = None,
                             is_builtin: bool = False) -> bool:
        """Adds or replaces a persona template."""
        sql = """
        INSERT OR REPLACE INTO PERSONA_TEMPLATES
            (template_id, name, display_name, avatar_url, system_prompt,
             model, provider, response_style, description, is_builtin, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        now = datetime.utcnow().isoformat()
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (template_id, name, display_name, avatar_url,
                                     system_prompt, model, provider, response_style,
                                     description, 1 if is_builtin else 0, now, now))
            logger.debug(f"Added/updated persona template: {template_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding persona template '{template_id}': {e}", exc_info=True)
            raise

    def get_persona_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Gets a persona template by ID."""
        sql = "SELECT * FROM PERSONA_TEMPLATES WHERE template_id = ?;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (template_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting persona template '{template_id}': {e}", exc_info=True)
            return None

    def get_all_persona_templates(self) -> List[Dict[str, Any]]:
        """Gets all persona templates."""
        sql = "SELECT * FROM PERSONA_TEMPLATES ORDER BY is_builtin DESC, name ASC;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting all persona templates: {e}", exc_info=True)
            return []

    def update_persona_template(self, template_id: str, **fields) -> bool:
        """Updates specific fields of a persona template."""
        allowed_fields = {'name', 'display_name', 'avatar_url', 'system_prompt',
                          'model', 'provider', 'response_style', 'description'}
        update_fields = {k: v for k, v in fields.items() if k in allowed_fields}
        if not update_fields:
            return False

        update_fields['updated_at'] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in update_fields)
        values = list(update_fields.values()) + [template_id]

        sql = f"UPDATE PERSONA_TEMPLATES SET {set_clause} WHERE template_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, values)
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error updating persona template '{template_id}': {e}", exc_info=True)
            raise

    def delete_persona_template(self, template_id: str) -> bool:
        """Deletes a persona template. Rejects deletion of built-in templates."""
        # Check if built-in
        template = self.get_persona_template(template_id)
        if template and template.get('is_builtin'):
            logger.warning(f"Cannot delete built-in persona template: {template_id}")
            return False

        sql = "DELETE FROM PERSONA_TEMPLATES WHERE template_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (template_id,))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Deleted persona template: {template_id}")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error deleting persona template '{template_id}': {e}", exc_info=True)
            raise

    def seed_builtin_templates(self, templates: List[Dict[str, Any]]) -> int:
        """Seeds built-in templates using INSERT OR IGNORE (idempotent)."""
        sql = """
        INSERT OR IGNORE INTO PERSONA_TEMPLATES
            (template_id, name, display_name, avatar_url, system_prompt,
             model, provider, response_style, description, is_builtin, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
        """
        now = datetime.utcnow().isoformat()
        count = 0
        try:
            with self._conn:
                cursor = self._conn.cursor()
                for t in templates:
                    cursor.execute(sql, (
                        t['template_id'], t['name'], t['display_name'],
                        t.get('avatar_url'), t.get('system_prompt'),
                        t.get('model'), t.get('provider'),
                        t.get('response_style'), t.get('description'), now
                    ))
                    if cursor.rowcount > 0:
                        count += 1
            if count > 0:
                logger.info(f"Seeded {count} built-in persona templates")
            return count
        except sqlite3.Error as e:
            logger.error(f"Error seeding persona templates: {e}", exc_info=True)
            raise

    # --- Channel Personas ---

    def set_channel_persona(self, channel_id: str, display_name: str,
                            avatar_url: Optional[str] = None,
                            system_prompt: Optional[str] = None,
                            model: Optional[str] = None,
                            provider: Optional[str] = None,
                            response_style: Optional[str] = None,
                            template_id: Optional[str] = None) -> bool:
        """Sets or replaces the persona for a channel."""
        now = datetime.utcnow().isoformat()
        # Preserve existing webhook credentials if updating
        existing = self.get_channel_persona(channel_id)
        webhook_id = existing.get('webhook_id') if existing else None
        webhook_token = existing.get('webhook_token') if existing else None
        is_active = existing.get('is_active', 1) if existing else 1

        sql = """
        INSERT OR REPLACE INTO CHANNEL_PERSONAS
            (channel_id, template_id, display_name, avatar_url, system_prompt,
             model, provider, response_style, webhook_id, webhook_token,
             is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        created_at = existing.get('created_at', now) if existing else now
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (
                    channel_id, template_id, display_name, avatar_url,
                    system_prompt, model, provider, response_style,
                    webhook_id, webhook_token, is_active, created_at, now
                ))
            logger.debug(f"Set persona for channel {channel_id}: {display_name}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error setting persona for channel '{channel_id}': {e}", exc_info=True)
            raise

    def get_channel_persona(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Gets the persona configuration for a channel."""
        sql = "SELECT * FROM CHANNEL_PERSONAS WHERE channel_id = ?;"
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting persona for channel '{channel_id}': {e}", exc_info=True)
            return None

    def get_all_channel_personas(self) -> List[Dict[str, Any]]:
        """Gets all channel persona configurations."""
        sql = """
        SELECT cp.*, pt.name as template_name
        FROM CHANNEL_PERSONAS cp
        LEFT JOIN PERSONA_TEMPLATES pt ON cp.template_id = pt.template_id
        ORDER BY cp.channel_id;
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error getting all channel personas: {e}", exc_info=True)
            return []

    def update_channel_persona_webhook(self, channel_id: str,
                                       webhook_id: Optional[str],
                                       webhook_token: Optional[str]) -> bool:
        """Updates the webhook credentials for a channel persona."""
        sql = """
        UPDATE CHANNEL_PERSONAS
        SET webhook_id = ?, webhook_token = ?, updated_at = ?
        WHERE channel_id = ?;
        """
        now = datetime.utcnow().isoformat()
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (webhook_id, webhook_token, now, channel_id))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Error updating webhook for channel '{channel_id}': {e}", exc_info=True)
            raise

    def toggle_channel_persona(self, channel_id: str) -> Optional[bool]:
        """Toggles the is_active flag for a channel persona. Returns new state or None."""
        persona = self.get_channel_persona(channel_id)
        if not persona:
            return None

        new_state = not bool(persona['is_active'])
        sql = "UPDATE CHANNEL_PERSONAS SET is_active = ?, updated_at = ? WHERE channel_id = ?;"
        now = datetime.utcnow().isoformat()
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (1 if new_state else 0, now, channel_id))
            logger.debug(f"Toggled persona for channel {channel_id}: active={new_state}")
            return new_state
        except sqlite3.Error as e:
            logger.error(f"Error toggling persona for channel '{channel_id}': {e}", exc_info=True)
            raise

    def remove_channel_persona(self, channel_id: str) -> bool:
        """Removes the persona for a channel."""
        sql = "DELETE FROM CHANNEL_PERSONAS WHERE channel_id = ?;"
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute(sql, (channel_id,))
                deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Removed persona for channel: {channel_id}")
            return deleted
        except sqlite3.Error as e:
            logger.error(f"Error removing persona for channel '{channel_id}': {e}", exc_info=True)
            raise
