"""Commands package initialization."""
from .user_commands import setup_user_commands
from .admin_commands import setup_admin_commands
from .upload_commands import setup_upload_commands

__all__ = ['setup_user_commands', 'setup_admin_commands', 'setup_upload_commands']