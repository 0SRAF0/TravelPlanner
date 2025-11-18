from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
from datetime import datetime
from app.db.database import get_database

router = APIRouter(prefix="/chat", tags=["Chat"])

# Store active connections: chatId -> [websocket1, websocket2, ...]
active_connections: Dict[str, List[WebSocket]] = {}


async def broadcast_to_chat(chat_id: str, message_data: dict):
  """
  Broadcast a message to all connected clients in a specific chat.
  Can be called from other modules (e.g., orchestrator).
  """
  if chat_id in active_connections:
    for connection in active_connections[chat_id]:
      try:
        await connection.send_json(message_data)
      except Exception as e:
        print(f"[broadcast] Failed to send to connection: {e}")


@router.websocket("/{chat_id}")
async def chat_websocket(websocket: WebSocket, chat_id: str):
  await websocket.accept()

  # Add to active connections
  if chat_id not in active_connections:
    active_connections[chat_id] = []
  active_connections[chat_id].append(websocket)

  try:
    while True:
      # Receive message from client
      data = await websocket.receive_json()

      # Get MongoDB collections
      db = get_database()
      messages_collection = db.messages

      # Save user message to MongoDB
      message_doc = {
        "chatId": chat_id,
        "senderId": data.get("senderId"),
        "senderName": data.get("senderName"),
        "content": data.get("content"),
        "type": "user",
        "createdAt": datetime.utcnow()
      }
      await messages_collection.insert_one(message_doc)

      # Broadcast user message to all clients in this chat
      for connection in active_connections[chat_id]:
        await connection.send_json(data)

      # Check if message contains "leggo" to trigger AI
      if "leggo" in data.get("content", "").lower():
        # Get full conversation history
        messages = await messages_collection.find(
          {"chatId": chat_id}
        ).sort("createdAt", 1).to_list(length=None)

        # Generate AI response
        ai_response = await generate_ai_response(messages)

        # Save AI message to MongoDB
        ai_message_doc = {
          "chatId": chat_id,
          "senderId": None,
          "senderName": "AI Assistant",
          "content": ai_response,
          "type": "ai",
          "createdAt": datetime.utcnow()
        }
        await messages_collection.insert_one(ai_message_doc)

        # Broadcast AI message to all clients
        ai_data = {
          "senderId": "ai",
          "senderName": "AI Assistant",
          "content": ai_response,
          "type": "ai",
          "timestamp": datetime.utcnow().isoformat()
        }
        for connection in active_connections[chat_id]:
          await connection.send_json(ai_data)

  except WebSocketDisconnect:
    # Remove from active connections
    active_connections[chat_id].remove(websocket)
    if not active_connections[chat_id]:
      del active_connections[chat_id]


async def generate_ai_response(messages: List[dict]) -> str:
  """
  Generate AI response based on conversation history.
  Replace this with your actual LLM integration.
  """
  # TODO: Replace with actual LLM call (OpenAI, Claude, etc.)
  # For now, a simple response

  # Build conversation context
  conversation = "\n".join([
    f"{msg['senderName']}: {msg['content']}"
    for msg in messages
    if msg['type'] == 'user'
  ])

  # Simple mock response - replace with actual LLM
  return f"Based on your discussion, I recommend starting with destination research. What's your group's budget range and preferred travel dates?"