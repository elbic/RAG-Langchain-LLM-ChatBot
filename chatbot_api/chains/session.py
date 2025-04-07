from typing import Dict, Optional
from uuid import uuid4
from .memory import ChatMemory

class SessionManager:
    """Manages multiple chat sessions."""
    def __init__(self):
        self.sessions: Dict[str, ChatMemory] = {}
    
    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new chat session.
        
        Args:
            session_id (Optional[str]): Custom session ID. If None, generates a UUID.
            
        Returns:
            str: The session ID
        """
        session_id = session_id or str(uuid4())
        self.sessions[session_id] = ChatMemory()
        return session_id
    
    def get_session(self, session_id: str) -> Optional[ChatMemory]:
        """Get a chat session by ID.
        
        Args:
            session_id (str): The session ID
            
        Returns:
            Optional[ChatMemory]: The chat memory for the session, or None if not found
        """
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> None:
        """Delete a chat session.
        
        Args:
            session_id (str): The session ID to delete
        """
        if session_id in self.sessions:
            del self.sessions[session_id] 