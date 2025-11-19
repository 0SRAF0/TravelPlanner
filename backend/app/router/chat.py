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
      users_collection = db.users
      trips_collection = db.trips
      preferences_collection = db.preferences

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

        # --- Fetch user preferences and trip details ---
        user_id = data.get("senderId")
        trip_id = chat_id
        user_pref = await preferences_collection.find_one({"user_id": user_id, "trip_id": trip_id})
        trip = await trips_collection.find_one({"_id": trip_id})
        user = await users_collection.find_one({"google_id": user_id})

        # Build context string
        context_lines = []
        if user:
          context_lines.append(f"User: {user.get('name', 'Unknown')}")
        if trip:
          context_lines.append(f"Trip: {trip.get('trip_name', 'N/A')}, Destination: {trip.get('destination', 'N/A')}")
        if user_pref:
          context_lines.append(f"Preferences: {user_pref.get('preferences', user_pref)}")

        # --- Aggregate votes for this trip and include a short summary in context ---
        try:
          votes_cursor = db.votes.find({"trip_id": trip_id})
          votes_list = await votes_cursor.to_list(length=None)
          if votes_list:
            tally = {}
            for v in votes_list:
              name = v.get("activity_name")
              if not name:
                continue
              if name not in tally:
                tally[name] = {"up": 0, "down": 0}
              if v.get("vote") == "up":
                tally[name]["up"] += 1
              else:
                tally[name]["down"] += 1

            # Build a compact votes summary: Activity (+ups/-downs), limit to top 5 by total votes
            summary_items = []
            sorted_items = sorted(tally.items(), key=lambda kv: (kv[1]["up"] + kv[1]["down"]), reverse=True)
            for name, counts in sorted_items[:5]:
              summary_items.append(f"{name} (+{counts['up']}/-{counts['down']})")

            if summary_items:
              context_lines.append(f"Votes summary: {', '.join(summary_items)}")
        except Exception as e:
          print(f"Warning: failed to aggregate votes for context: {e}")
        context = " | ".join(context_lines)

        # Generate AI response with context
        ai_response = await generate_ai_response(messages, context)

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


async def generate_ai_response(messages: List[dict], context: str = "") -> str:
  """
  Generate AI response based on conversation history.
  Replace this with your actual LLM integration.
  """
  from app.core.config import GOOGLE_AI_API_KEY, GOOGLE_AI_MODEL

  if not GOOGLE_AI_API_KEY:
    return "I'm sorry, but I'm not correctly configured to answer right now (Missing API Key)."

  try:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(
        model=GOOGLE_AI_MODEL, temperature=0.7, api_key=GOOGLE_AI_API_KEY
    )
    # Build conversation context with extra context
    system_prompt = f"""You are a helpful AI travel planning assistant for a group travel planning application. 
    Your role is to help users plan their trips by:
    - Answering questions about travel destinations, activities, and planning
    - Providing suggestions for group travel
    - Helping with itinerary planning
    - Answering questions about preferences, budgets, and travel logistics
    - Being friendly, informative, and concise
    Keep your responses conversational and helpful. If you don't know something, admit it rather than making things up.

    Context for this conversation: {context}
    """
    # Format conversation history using LangChain message types
    langchain_messages = [SystemMessage(content=system_prompt)]
    # Add history (limit to last 10 messages to avoid token limits)
    # Filter for user and ai messages only
    relevant_messages = [m for m in messages if m.get('type') in ['user', 'ai']]
    recent_history = relevant_messages[-10:]

    for msg in recent_history:
        role = msg.get("type")
        content = msg.get("content", "")
        if content:
            if role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "ai":
                langchain_messages.append(AIMessage(content=content))
    # Get response from LLM
    response = await llm.ainvoke(langchain_messages)
    return response.content if hasattr(response, "content") else str(response)

  except Exception as e:
    print(f"Error generating AI response: {e}")
    return "I'm having trouble thinking right now. Please try again later."
