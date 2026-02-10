"""
Config Backup Module

Handles backup and restore of device configurations:
- Store configs with versioning
- Diff between versions
- Restore to previous versions
"""
import os
import json
import sqlite3
import difflib
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ConfigVersion:
    """A configuration version"""
    id: int
    device_id: str
    device_name: str
    version: int
    config_content: str
    config_type: str  # running, startup, etc.
    timestamp: str
    description: str
    size_bytes: int
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "version": self.version,
            "config_type": self.config_type,
            "timestamp": self.timestamp,
            "description": self.description,
            "size_bytes": self.size_bytes
        }


class ConfigBackupManager:
    """
    Manages device configuration backups
    
    Features:
    - SQLite storage for configs
    - Version history
    - Diff comparison
    - Restore functionality
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "data", 
                "config_backups.db"
            )
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                device_name TEXT NOT NULL,
                version INTEGER NOT NULL,
                config_content TEXT NOT NULL,
                config_type TEXT DEFAULT 'running',
                timestamp TEXT NOT NULL,
                description TEXT,
                size_bytes INTEGER,
                UNIQUE(device_id, version)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_device_id 
            ON config_backups(device_id)
        """)
        
        conn.commit()
        conn.close()
    
    def backup_config(
        self,
        device_id: str,
        device_name: str,
        config_content: str,
        config_type: str = "running",
        description: str = ""
    ) -> ConfigVersion:
        """
        Create a new config backup
        
        Args:
            device_id: Device identifier
            device_name: Device display name
            config_content: The configuration text
            config_type: Type (running, startup, etc.)
            description: Optional description
            
        Returns:
            Created ConfigVersion
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get next version number
        cursor.execute("""
            SELECT COALESCE(MAX(version), 0) + 1 
            FROM config_backups 
            WHERE device_id = ?
        """, (device_id,))
        next_version = cursor.fetchone()[0]
        
        timestamp = datetime.now().isoformat()
        size_bytes = len(config_content.encode('utf-8'))
        
        cursor.execute("""
            INSERT INTO config_backups 
            (device_id, device_name, version, config_content, config_type, 
             timestamp, description, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (device_id, device_name, next_version, config_content, 
              config_type, timestamp, description, size_bytes))
        
        config_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return ConfigVersion(
            id=config_id,
            device_id=device_id,
            device_name=device_name,
            version=next_version,
            config_content=config_content,
            config_type=config_type,
            timestamp=timestamp,
            description=description,
            size_bytes=size_bytes
        )
    
    def get_versions(self, device_id: str) -> List[ConfigVersion]:
        """Get all version history for a device"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, device_id, device_name, version, config_content,
                   config_type, timestamp, description, size_bytes
            FROM config_backups
            WHERE device_id = ?
            ORDER BY version DESC
        """, (device_id,))
        
        versions = []
        for row in cursor.fetchall():
            versions.append(ConfigVersion(
                id=row[0],
                device_id=row[1],
                device_name=row[2],
                version=row[3],
                config_content=row[4],
                config_type=row[5],
                timestamp=row[6],
                description=row[7],
                size_bytes=row[8]
            ))
        
        conn.close()
        return versions
    
    def get_version(self, device_id: str, version: int) -> Optional[ConfigVersion]:
        """Get a specific version"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, device_id, device_name, version, config_content,
                   config_type, timestamp, description, size_bytes
            FROM config_backups
            WHERE device_id = ? AND version = ?
        """, (device_id, version))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return ConfigVersion(
                id=row[0],
                device_id=row[1],
                device_name=row[2],
                version=row[3],
                config_content=row[4],
                config_type=row[5],
                timestamp=row[6],
                description=row[7],
                size_bytes=row[8]
            )
        return None
    
    def get_latest_version(self, device_id: str) -> Optional[ConfigVersion]:
        """Get the latest version for a device"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, device_id, device_name, version, config_content,
                   config_type, timestamp, description, size_bytes
            FROM config_backups
            WHERE device_id = ?
            ORDER BY version DESC
            LIMIT 1
        """, (device_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return ConfigVersion(
                id=row[0],
                device_id=row[1],
                device_name=row[2],
                version=row[3],
                config_content=row[4],
                config_type=row[5],
                timestamp=row[6],
                description=row[7],
                size_bytes=row[8]
            )
        return None
    
    def compare_versions(
        self, 
        device_id: str, 
        version1: int, 
        version2: int
    ) -> Dict[str, Any]:
        """
        Compare two configuration versions
        
        Returns:
            Dict with diff information
        """
        v1 = self.get_version(device_id, version1)
        v2 = self.get_version(device_id, version2)
        
        if not v1 or not v2:
            return {"error": "One or both versions not found"}
        
        # Generate diff
        v1_lines = v1.config_content.splitlines(keepends=True)
        v2_lines = v2.config_content.splitlines(keepends=True)
        
        diff = list(difflib.unified_diff(
            v1_lines, 
            v2_lines,
            fromfile=f"Version {version1} ({v1.timestamp[:19]})",
            tofile=f"Version {version2} ({v2.timestamp[:19]})"
        ))
        
        # Count changes
        additions = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
        
        return {
            "device_id": device_id,
            "version1": version1,
            "version2": version2,
            "diff": "".join(diff),
            "additions": additions,
            "deletions": deletions,
            "total_changes": additions + deletions
        }
    
    def delete_version(self, device_id: str, version: int) -> bool:
        """Delete a specific version"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM config_backups
            WHERE device_id = ? AND version = ?
        """, (device_id, version))
        
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return deleted
    
    def get_all_devices(self) -> List[Dict[str, Any]]:
        """Get list of all devices with backups"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT device_id, device_name, 
                   COUNT(*) as version_count,
                   MAX(timestamp) as last_backup
            FROM config_backups
            GROUP BY device_id
            ORDER BY last_backup DESC
        """)
        
        devices = []
        for row in cursor.fetchall():
            devices.append({
                "device_id": row[0],
                "device_name": row[1],
                "version_count": row[2],
                "last_backup": row[3]
            })
        
        conn.close()
        return devices
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """Get backup statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(DISTINCT device_id) FROM config_backups")
        device_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM config_backups")
        total_backups = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(size_bytes) FROM config_backups")
        total_size = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT MAX(timestamp) FROM config_backups")
        last_backup = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_devices": device_count,
            "total_backups": total_backups,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "last_backup": last_backup
        }


# Singleton instance
config_backup = ConfigBackupManager()
