"""SQLite 初始化和连接工具。

数据库层独立于 NoneBot，后续迁移到 Go 时可以保留表结构和业务约定。
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def database_path() -> Path:
    """返回数据库文件路径，并确保父目录存在。"""
    configured_path = os.getenv("QQBOT_DATABASE_PATH", "data/qqbot.db")
    path = Path(configured_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    """创建一个带行对象支持的 SQLite 连接。"""
    connection = sqlite3.connect(database_path())
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    """创建第一版基础表。重复执行是安全的。"""
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                nickname TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                group_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sign_ins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                sign_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, sign_date)
            );

            CREATE TABLE IF NOT EXISTS cultivators (
                user_id TEXT PRIMARY KEY,
                nickname TEXT NOT NULL DEFAULT '',
                realm_index INTEGER NOT NULL DEFAULT 0,
                experience INTEGER NOT NULL DEFAULT 0,
                spirit_stones INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS group_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                nickname TEXT NOT NULL DEFAULT '',
                message_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_group_messages_group_time
                ON group_messages (group_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_group_messages_group_user
                ON group_messages (group_id, user_id);

            CREATE TABLE IF NOT EXISTS ai_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_ai_memories_scope_time
                ON ai_memories (scope_id, id);

            CREATE TABLE IF NOT EXISTS ai_personas (
                scope_id TEXT PRIMARY KEY,
                persona_key TEXT NOT NULL DEFAULT '',
                custom_prompt TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ai_summaries (
                scope_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL DEFAULT '',
                upto_id INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ai_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_ai_facts_scope_id
                ON ai_facts (scope_id, id);

            CREATE TABLE IF NOT EXISTS ai_voice_modes (
                scope_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
