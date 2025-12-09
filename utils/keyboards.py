"""
Inline keyboard builder utilities for the Telegram Card Bot.
Provides reusable keyboard templates for various bot interactions.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Optional, Tuple
from .rarity import RARITIES


class Keyboards:
    """Factory class for creating inline keyboards."""
    
    # ===== General Keyboards =====
    
    @staticmethod
    def confirm_cancel() -> InlineKeyboardMarkup:
        """Create confirm/cancel keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data="confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def back_cancel() -> InlineKeyboardMarkup:
        """Create back/cancel keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("⬅️ Back", callback_data="back"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ===== Rarity Selection =====
    
    @staticmethod
    def rarity_selection(selected_id: Optional[int] = None) -> InlineKeyboardMarkup:
        """
        Create rarity selection keyboard.
        
        Args:
            selected_id: Currently selected rarity ID (optional)
        """
        keyboard = []
        row = []
        
        for i, (rid, rarity) in enumerate(RARITIES.items()):
            # Mark selected rarity
            prefix = "✓ " if rid == selected_id else ""
            button = InlineKeyboardButton(
                f"{prefix}{rarity.emoji} {rarity.name}",
                callback_data=f"rarity_{rid}"
            )
            row.append(button)
            
            # 2 buttons per row
            if len(row) == 2:
                keyboard.append(row)
                row = []
        
        # Add remaining buttons
        if row:
            keyboard.append(row)
        
        # Add confirm/cancel
        keyboard.append([
            InlineKeyboardButton("✅ Confirm", callback_data="confirm_rarity"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    # ===== Upload Flow Keyboards =====
    
    @staticmethod
    def anime_selection(animes: List[Tuple[int, str]], page: int = 0, 
                        per_page: int = 8) -> InlineKeyboardMarkup:
        """
        Create anime selection keyboard with pagination.
        
        Args:
            animes: List of (id, name) tuples
            page: Current page number
            per_page: Items per page
        """
        keyboard = []
        
        # Calculate pagination
        start = page * per_page
        end = start + per_page
        page_animes = animes[start:end]
        
        # Add anime buttons
        for anime_id, anime_name in page_animes:
            display_name = anime_name[:30] + "..." if len(anime_name) > 30 else anime_name
            keyboard.append([
                InlineKeyboardButton(f"🎬 {display_name}", 
                                     callback_data=f"anime_{anime_id}")
            ])
        
        # Add "Add New" option
        keyboard.append([
            InlineKeyboardButton("➕ Add New Anime", callback_data="add_new_anime")
        ])
        
        # Pagination buttons
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", 
                                                callback_data=f"anime_page_{page-1}"))
        if end < len(animes):
            nav_row.append(InlineKeyboardButton("➡️ Next", 
                                                callback_data=f"anime_page_{page+1}"))
        if nav_row:
            keyboard.append(nav_row)
        
        # Cancel button
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def character_selection(characters: List[Tuple[int, str]], anime_id: int,
                           page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
        """
        Create character selection keyboard with pagination.
        
        Args:
            characters: List of (id, name) tuples
            anime_id: Current anime ID
            page: Current page number
            per_page: Items per page
        """
        keyboard = []
        
        # Calculate pagination
        start = page * per_page
        end = start + per_page
        page_chars = characters[start:end]
        
        # Add character buttons
        for char_id, char_name in page_chars:
            display_name = char_name[:25] + "..." if len(char_name) > 25 else char_name
            keyboard.append([
                InlineKeyboardButton(f"👤 {display_name}", 
                                     callback_data=f"char_{char_id}")
            ])
        
        # Add "Add New" option
        keyboard.append([
            InlineKeyboardButton("➕ Add New Character", callback_data="add_new_character")
        ])
        
        # Pagination buttons
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", 
                                                callback_data=f"char_page_{page-1}"))
        if end < len(characters):
            nav_row.append(InlineKeyboardButton("➡️ Next", 
                                                callback_data=f"char_page_{page+1}"))
        if nav_row:
            keyboard.append(nav_row)
        
        # Back and Cancel
        keyboard.append([
            InlineKeyboardButton("⬅️ Back to Anime", callback_data="back_to_anime"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def upload_preview() -> InlineKeyboardMarkup:
        """Create upload preview keyboard with confirm/edit/cancel."""
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm & Save", callback_data="upload_confirm")
            ],
            [
                InlineKeyboardButton("✏️ Edit Anime", callback_data="edit_anime"),
                InlineKeyboardButton("✏️ Edit Character", callback_data="edit_character")
            ],
            [
                InlineKeyboardButton("✏️ Edit Rarity", callback_data="edit_rarity"),
                InlineKeyboardButton("📷 Change Photo", callback_data="edit_photo")
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ===== Harem/Collection Keyboards =====
    
    @staticmethod
    def harem_pagination(user_id: int, current_page: int, total_pages: int,
                         rarity_filter: Optional[int] = None) -> InlineKeyboardMarkup:
        """
        Create harem pagination keyboard.
        
        Args:
            user_id: User ID for callback data
            current_page: Current page number
            total_pages: Total number of pages
            rarity_filter: Optional rarity filter
        """
        keyboard = []
        nav_row = []
        
        # Previous button
        if current_page > 0:
            nav_row.append(InlineKeyboardButton(
                "⬅️", callback_data=f"harem_{user_id}_{current_page-1}_{rarity_filter or 0}"
            ))
        
        # Page indicator
        nav_row.append(InlineKeyboardButton(
            f"📄 {current_page + 1}/{total_pages}",
            callback_data="noop"
        ))
        
        # Next button
        if current_page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(
                "➡️", callback_data=f"harem_{user_id}_{current_page+1}_{rarity_filter or 0}"
            ))
        
        keyboard.append(nav_row)
        
        # Rarity filter row
        filter_row = [
            InlineKeyboardButton("🎯 Filter by Rarity", callback_data="harem_filter_menu")
        ]
        keyboard.append(filter_row)
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def harem_rarity_filter() -> InlineKeyboardMarkup:
        """Create rarity filter menu for harem."""
        keyboard = [[InlineKeyboardButton("📋 All Rarities", callback_data="harem_filter_0")]]
        
        row = []
        for rid, rarity in RARITIES.items():
            button = InlineKeyboardButton(
                f"{rarity.emoji}", callback_data=f"harem_filter_{rid}"
            )
            row.append(button)
            
            if len(row) == 4:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="harem_back")])
        
        return InlineKeyboardMarkup(keyboard)
    
    # ===== Card Detail Keyboards =====
    
    @staticmethod
    def card_detail(card_id: int, is_admin: bool = False) -> InlineKeyboardMarkup:
        """
        Create card detail keyboard.
        
        Args:
            card_id: Card ID
            is_admin: Whether user is admin
        """
        keyboard = []
        
        if is_admin:
            keyboard.append([
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit_card_{card_id}"),
                InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_card_{card_id}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("👥 Owners List", callback_data=f"card_owners_{card_id}")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    # ===== Search Results Keyboards =====
    
    @staticmethod
    def search_results(cards: List[Tuple[int, str, str, int]], 
                       page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
        """
        Create search results keyboard.
        
        Args:
            cards: List of (id, character, anime, rarity_id) tuples
            page: Current page
            per_page: Items per page
        """
        keyboard = []
        
        start = page * per_page
        end = start + per_page
        page_cards = cards[start:end]
        
        for card_id, character, anime, rarity_id in page_cards:
            rarity = RARITIES.get(rarity_id)
            emoji = rarity.emoji if rarity else "❓"
            display = f"{emoji} {character[:20]}"
            keyboard.append([
                InlineKeyboardButton(display, callback_data=f"view_card_{card_id}")
            ])
        
        # Pagination
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"search_page_{page-1}"))
        
        nav_row.append(InlineKeyboardButton(
            f"📄 {page + 1}/{(len(cards) + per_page - 1) // per_page}",
            callback_data="noop"
        ))
        
        if end < len(cards):
            nav_row.append(InlineKeyboardButton("➡️", callback_data=f"search_page_{page+1}"))
        
        keyboard.append(nav_row)
        
        return InlineKeyboardMarkup(keyboard)
    
    # ===== Admin Keyboards =====
    
    @staticmethod
    def role_selection(target_user_id: int) -> InlineKeyboardMarkup:
        """Create role selection keyboard."""
        roles = [
            ("👤 User", "user"),
            ("📤 Uploader", "uploader"),
            ("🛡️ Admin", "admin"),
            ("💻 Developer", "dev"),
            ("👑 Owner", "owner")
        ]
        
        keyboard = []
        row = []
        
        for label, role in roles:
            button = InlineKeyboardButton(
                label, callback_data=f"setrole_{target_user_id}_{role}"
            )
            row.append(button)
            
            if len(row) == 2:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def edit_card_menu(card_id: int) -> InlineKeyboardMarkup:
        """Create card edit menu."""
        keyboard = [
            [
                InlineKeyboardButton("🎬 Edit Anime", callback_data=f"cedit_anime_{card_id}"),
                InlineKeyboardButton("👤 Edit Character", callback_data=f"cedit_char_{card_id}")
            ],
            [
                InlineKeyboardButton("⭐ Edit Rarity", callback_data=f"cedit_rarity_{card_id}"),
                InlineKeyboardButton("📷 Edit Photo", callback_data=f"cedit_photo_{card_id}")
            ],
            [
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def delete_confirm(card_id: int) -> InlineKeyboardMarkup:
        """Create delete confirmation keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, Delete", callback_data=f"confirm_delete_{card_id}"),
                InlineKeyboardButton("❌ No, Cancel", callback_data="cancel")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ===== Catch Keyboard =====
    
    @staticmethod
    def catch_card(card_id: int) -> InlineKeyboardMarkup:
        """Create catch card keyboard."""
        keyboard = [
            [InlineKeyboardButton("🎴 View Card Details", callback_data=f"view_card_{card_id}")],
            [InlineKeyboardButton("🎒 View My Collection", callback_data="my_harem")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    # ===== Stats Keyboard =====
    
    @staticmethod
    def admin_stats() -> InlineKeyboardMarkup:
        """Create admin stats keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("👥 User Stats", callback_data="stats_users"),
                InlineKeyboardButton("🎴 Card Stats", callback_data="stats_cards")
            ],
            [
                InlineKeyboardButton("📊 Catch Stats", callback_data="stats_catches"),
                InlineKeyboardButton("🔄 Refresh", callback_data="stats_refresh")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)