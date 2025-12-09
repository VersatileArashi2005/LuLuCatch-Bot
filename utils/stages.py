"""
Stage management for multi-step workflows like card uploading.
"""

from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio


class Stages(Enum):
    """Enumeration of all possible stages in workflows."""
    
    # No active workflow
    NONE = "none"
    
    # Upload workflow stages
    ANIME_SELECT = "anime_select"
    ADDING_ANIME = "adding_anime"
    CHARACTER_SELECT = "character_select"
    ADDING_CHARACTER = "adding_character"
    RARITY_SELECT = "rarity_select"
    AWAITING_PHOTO = "awaiting_photo"
    CONFIRM_PHOTO = "confirm_photo"
    
    # Edit workflow stages
    AWAITING_NEW_VALUE = "awaiting_new_value"
    AWAITING_NEW_PHOTO = "awaiting_new_photo"
    
    # Search workflow
    SEARCH_RESULTS = "search_results"


class StageData:
    """Container for stage-related data."""
    
    def __init__(self):
        self.stage: Stages = Stages.NONE
        self.data: Dict[str, Any] = {}
        self.created_at: datetime = datetime.utcnow()
        self.expires_at: datetime = datetime.utcnow() + timedelta(minutes=30)
    
    def is_expired(self) -> bool:
        """Check if the stage data has expired."""
        return datetime.utcnow() > self.expires_at
    
    def refresh(self):
        """Refresh the expiration time."""
        self.expires_at = datetime.utcnow() + timedelta(minutes=30)
    
    def set(self, key: str, value: Any):
        """Set a data value and refresh expiration."""
        self.data[key] = value
        self.refresh()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a data value."""
        return self.data.get(key, default)
    
    def clear(self):
        """Clear all stage data."""
        self.stage = Stages.NONE
        self.data = {}


class StageManager:
    """
    Manager for tracking user workflow stages.
    Handles multi-step processes like card uploading and editing.
    """
    
    def __init__(self):
        self._stages: Dict[int, StageData] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start_cleanup_task(self):
        """Start background task to cleanup expired stages."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self):
        """Background loop to cleanup expired stages."""
        while True:
            await asyncio.sleep(300)  # Run every 5 minutes
            self._cleanup_expired()
    
    def _cleanup_expired(self):
        """Remove expired stage data."""
        expired_users = [
            user_id for user_id, data in self._stages.items()
            if data.is_expired()
        ]
        for user_id in expired_users:
            del self._stages[user_id]
    
    def get_stage(self, user_id: int) -> Stages:
        """
        Get current stage for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Current stage enum
        """
        if user_id not in self._stages:
            return Stages.NONE
        
        data = self._stages[user_id]
        if data.is_expired():
            del self._stages[user_id]
            return Stages.NONE
        
        return data.stage
    
    def set_stage(self, user_id: int, stage: Stages):
        """
        Set stage for a user.
        
        Args:
            user_id: Telegram user ID
            stage: Stage to set
        """
        if user_id not in self._stages:
            self._stages[user_id] = StageData()
        
        self._stages[user_id].stage = stage
        self._stages[user_id].refresh()
    
    def get_data(self, user_id: int) -> StageData:
        """
        Get full stage data for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            StageData object
        """
        if user_id not in self._stages:
            self._stages[user_id] = StageData()
        return self._stages[user_id]
    
    def set_data(self, user_id: int, key: str, value: Any):
        """
        Set a specific data value for a user.
        
        Args:
            user_id: Telegram user ID
            key: Data key
            value: Data value
        """
        if user_id not in self._stages:
            self._stages[user_id] = StageData()
        
        self._stages[user_id].set(key, value)
    
    def get_value(self, user_id: int, key: str, default: Any = None) -> Any:
        """
        Get a specific data value for a user.
        
        Args:
            user_id: Telegram user ID
            key: Data key
            default: Default value if not found
            
        Returns:
            The stored value or default
        """
        if user_id not in self._stages:
            return default
        
        return self._stages[user_id].get(key, default)
    
    def clear(self, user_id: int):
        """
        Clear all stage data for a user.
        
        Args:
            user_id: Telegram user ID
        """
        if user_id in self._stages:
            self._stages[user_id].clear()
    
    def is_in_workflow(self, user_id: int) -> bool:
        """
        Check if user is currently in a workflow.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if user has an active stage
        """
        return self.get_stage(user_id) != Stages.NONE


# Global stage manager instance
stage_manager = StageManager()