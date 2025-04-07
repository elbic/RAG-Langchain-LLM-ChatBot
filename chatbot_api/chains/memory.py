import time
from typing import Dict, List, Optional
from collections import deque
from dataclasses import dataclass, field

@dataclass
class Message:
    """Represents a single message in the chat history."""
    role: str  # 'human' or 'ai'
    content: str
    timestamp: float = field(default_factory=lambda: time.time())

class ChatMemory:
    """Manages chat history with a fixed size circular buffer."""
    def __init__(self, max_messages: int = 10):
        """Initialize chat memory.
        
        Args:
            max_messages (int): Maximum number of messages to store in history.
        """
        self.messages: deque = deque(maxlen=max_messages)
    
    def add_message(self, role: str, content: str) -> None:
        """Add a new message to the history.
        
        Args:
            role (str): Role of the message sender ('human' or 'ai')
            content (str): Content of the message
        """
        message = Message(role=role, content=content)
        self.messages.append(message)
    
    def get_history(self) -> List[Dict[str, str]]:
        """Get the chat history in the format expected by ChatRequest.
        
        Returns:
            List[Dict[str, str]]: List of messages in the format {'human': str} or {'ai': str}
        """
        return [
            {message.role: message.content}
            for message in self.messages
        ]
    
    def clear(self) -> None:
        """Clear the chat history."""
        self.messages.clear() 