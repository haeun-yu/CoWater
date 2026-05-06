"""WebSocket Pub/Sub manager for real-time mission updates"""

import asyncio
import json
import logging
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PubSubManager:
    """Manages WebSocket connections and pub/sub channels"""
    
    def __init__(self) -> None:
        # connections[channel] = {connection_id: websocket}
        self.connections: Dict[str, Dict[str, any]] = {}
        self.subscribers: Dict[str, List[str]] = {}  # channel → [connection_ids]
    
    async def connect(self, channel: str, connection_id: str, websocket) -> None:
        """Subscribe connection to channel"""
        if channel not in self.connections:
            self.connections[channel] = {}
        
        self.connections[channel][connection_id] = websocket
        
        if channel not in self.subscribers:
            self.subscribers[channel] = []
        self.subscribers[channel].append(connection_id)
        
        logger.info(f"✅ Connection {connection_id} subscribed to channel: {channel}")
    
    async def disconnect(self, channel: str, connection_id: str) -> None:
        """Unsubscribe connection from channel"""
        if channel in self.connections and connection_id in self.connections[channel]:
            del self.connections[channel][connection_id]
        
        if channel in self.subscribers and connection_id in self.subscribers[channel]:
            self.subscribers[channel].remove(connection_id)
        
        logger.info(f"✅ Connection {connection_id} disconnected from channel: {channel}")
    
    async def publish(self, channel: str, message: Dict) -> None:
        """Publish message to all subscribers of channel"""
        if channel not in self.connections:
            return
        
        # Send to all connections in channel
        disconnected = []
        for connection_id, websocket in self.connections[channel].items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"⚠️ Failed to send message to {connection_id}: {e}")
                disconnected.append(connection_id)
        
        # Clean up disconnected clients
        for connection_id in disconnected:
            await self.disconnect(channel, connection_id)
    
    async def broadcast(self, message: Dict, exclude_channel: Optional[str] = None) -> None:
        """Broadcast message to all channels (except one)"""
        for channel in list(self.connections.keys()):
            if exclude_channel and channel == exclude_channel:
                continue
            await self.publish(channel, message)
    
    def get_subscriber_count(self, channel: str) -> int:
        """Get number of subscribers for channel"""
        return len(self.subscribers.get(channel, []))
    
    def get_channels(self) -> List[str]:
        """Get all active channels"""
        return list(self.connections.keys())


# Global pub/sub manager instance
pubsub_manager: Optional[PubSubManager] = None


def get_pubsub_manager() -> PubSubManager:
    """Get or create global pub/sub manager"""
    global pubsub_manager
    
    if pubsub_manager is None:
        pubsub_manager = PubSubManager()
    
    return pubsub_manager
