from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from typing import Dict, List
from datetime import datetime
from app.db.database import get_database
from app.models.common import APIResponse

async def handle_heyai_command(message: str, user_id: str, trip_id: str):
    """
    Handle heyAI commands from chat.
    Commands start with 'heyAI' (case insensitive).
    """
    # Remove 'heyAI' prefix (case insensitive)
    command = message[5:].strip()
    
    if not command:
        return
    
    db = get_database()
    messages_collection = db.messages
    users_collection = db.users
    
    # Get user name
    user = await users_collection.find_one({"google_id": user_id})
    user_name = user.get("name", "Someone") if user else "Someone"
    
    # Create change request message
    request_msg = {
        "chatId": trip_id,
        "senderId": "system",
        "senderName": "AI Assistant",
        "content": f"{user_name} wants to: {command}\n\nReact 👍 to approve this change, otherwise we'll keep the current decision.\n\nNeed majority approval to proceed.",
        "type": "change_request",
        "change_data": {
            "requested_by": user_id,
            "command": command,
            "reactions": {},  # user_id: emoji
            "status": "pending",
            "approvals_needed": 0,  # Will be calculated based on trip members
            "approvals_current": 0
        },
        "createdAt": datetime.utcnow()
    }
    
    # Save to messages collection
    result = await messages_collection.insert_one(request_msg)
    message_id = str(result.inserted_id)
    
    # Add message_id to the response
    request_msg["_id"] = message_id
    request_msg["message_id"] = message_id
    
    # Broadcast to all clients
    await broadcast_to_chat(trip_id, {
        "senderId": "system",
        "senderName": "AI Assistant",
        "content": request_msg["content"],
        "type": "change_request",
        "message_id": message_id,
        "change_data": request_msg["change_data"],
        "timestamp": datetime.utcnow().isoformat()
    })

async def execute_change_request(trip_id: str, command: str, requested_by: str):
    """
    Execute an approved change request.
    Parses command and makes appropriate changes.
    """
    command_lower = command.lower().strip()
    
    db = get_database()
    trips = db.trips
    
    try:
        # Get trip
        try:
            trip = await trips.find_one({"_id": ObjectId(trip_id)})
        except:
            trip = await trips.find_one({"trip_code": trip_id.upper()})
        
        if not trip:
            return
        
        # Parse command type
        if "destination" in command_lower:
            # Extract destination (everything after "destination to")
            if "to" in command_lower:
                new_dest = command.split("to", 1)[1].strip()
                await trips.update_one(
                    {"_id": trip["_id"]},
                    {"$set": {"destination": new_dest, "updated_at": datetime.utcnow()}}
                )
                await broadcast_to_chat(trip_id, {
                    "senderId": "system",
                    "senderName": "AI Assistant",
                    "content": f"✅ Destination changed to: {new_dest}",
                    "type": "ai",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        elif "remove" in command_lower:
            # Remove activity
            activity_name = command.replace("remove", "").strip()
            col = get_activities_collection()
            result = await col.delete_one({"trip_id": trip_id, "name": {"$regex": activity_name, "$options": "i"}})
            
            if result.deleted_count > 0:
                await broadcast_to_chat(trip_id, {
                    "senderId": "system",
                    "senderName": "AI Assistant",
                    "content": f"Removed activity: {activity_name}",
                    "type": "ai",
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                await broadcast_to_chat(trip_id, {
                    "senderId": "system",
                    "senderName": "AI Assistant",
                    "content": f"Could not find activity: {activity_name}",
                    "type": "ai",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        elif "add" in command_lower or "suggest" in command_lower:
            # For now, just acknowledge
            await broadcast_to_chat(trip_id, {
                "senderId": "system",
                "senderName": "AI Assistant",
                "content": f"I'll work on: {command}\n\n(Full implementation coming soon)",
                "type": "ai",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        else:
            # Generic acknowledgment
            await broadcast_to_chat(trip_id, {
                "senderId": "system",
                "senderName": "AI Assistant",
                "content": f"✅ Change applied: {command}",
                "type": "ai",
                "timestamp": datetime.utcnow().isoformat()
            })
    
    except Exception as e:
        print(f"[execute_change_request] Error: {e}")
        await broadcast_to_chat(trip_id, {
            "senderId": "system",
            "senderName": "AI Assistant",
            "content": f"❌ Failed to execute: {command}",
            "type": "ai",
            "timestamp": datetime.utcnow().isoformat()
        })
        
router = APIRouter(prefix="/chat", tags=["Chat"])

# Store active connections: chatId -> [websocket1, websocket2, ...]
active_connections: Dict[str, List[WebSocket]] = {}


async def broadcast_to_chat(chat_id: str, message_data: dict):
  """
  Broadcast a message to all connected clients in a specific chat.
  Also saves the message to database for persistence.
  Can be called from other modules (e.g., orchestrator).
  """
  # Save message to database (except for status-only messages)
  msg_type = message_data.get('type', 'unknown')
  
  try:
    db = get_database()
    messages_collection = db.messages
    
    # Handle vote_update - update existing voting message
    if msg_type == 'vote_update':
      phase = message_data.get("phase")
      if phase:
        await messages_collection.update_one(
          {"chatId": chat_id, "type": "voting", "phase": phase},
          {"$set": {"options": message_data.get("options", [])}}
        )
        print(f"[broadcast] Updated voting options for phase {phase} in database")
    
    # Save new messages to database for persistence
    elif msg_type in ['ai', 'voting', 'change_request', 'system', 'agent_status']:
      # Prepare message document
      message_doc = {
        "chatId": chat_id,
        "senderId": message_data.get("senderId", "system"),
        "senderName": message_data.get("senderName", "AI Assistant"),
        "content": message_data.get("content", ""),
        "type": msg_type,
        "createdAt": datetime.utcnow()
      }
      
      # Add type-specific fields
      if msg_type == "voting":
        message_doc["phase"] = message_data.get("phase")
        message_doc["options"] = message_data.get("options", [])
      elif msg_type == "change_request":
        message_doc["message_id"] = message_data.get("message_id")
        message_doc["change_data"] = message_data.get("change_data", {})
      elif msg_type == "agent_status":
        message_doc["agent_name"] = message_data.get("agent_name")
        message_doc["status"] = message_data.get("status")
        message_doc["step"] = message_data.get("step")
        message_doc["progress"] = message_data.get("progress")
        message_doc["elapsed_seconds"] = message_data.get("elapsed_seconds")
      
      await messages_collection.insert_one(message_doc)
      print(f"[broadcast] Saved {msg_type} message to database for chat {chat_id}")
  except Exception as e:
    print(f"[broadcast] Warning: Failed to save/update message in database: {e}")
  
  # Broadcast to connected clients
  if chat_id in active_connections:
    print(f"[broadcast] Broadcasting {msg_type} to {len(active_connections[chat_id])} clients in chat {chat_id}")
    for connection in active_connections[chat_id]:
      try:
        await connection.send_json(message_data)
      except Exception as e:
        print(f"[broadcast] Failed to send to connection: {e}")
  else:
    print(f"[broadcast] No active connections for chat {chat_id}, message saved to DB but not broadcast")


@router.get("/messages/{chat_id}", response_model=APIResponse)
async def get_chat_messages(
    chat_id: str,
    limit: int = Query(default=100, description="Number of messages to return")
):
  """
  Fetch historical chat messages for a specific trip/chat.
  Returns messages sorted by creation time (oldest first).
  """
  try:
    db = get_database()
    messages_collection = db.messages
    
    # Query messages for this chat
    cursor = messages_collection.find({"chatId": chat_id}).sort("createdAt", 1).limit(limit)
    messages = await cursor.to_list(length=limit)
    
    # Format messages for frontend
    formatted_messages = []
    for msg in messages:
      formatted_msg = {
        "senderId": msg.get("senderId"),
        "senderName": msg.get("senderName"),
        "content": msg.get("content", ""),
        "type": msg.get("type", "user"),
        "timestamp": msg.get("createdAt").isoformat() if msg.get("createdAt") else datetime.utcnow().isoformat()
      }
      
      # Include additional fields for specific message types
      if msg.get("type") == "voting":
        formatted_msg["phase"] = msg.get("phase")
        formatted_msg["options"] = msg.get("options", [])
      elif msg.get("type") == "agent_status":
        formatted_msg["agent_name"] = msg.get("agent_name")
        formatted_msg["status"] = msg.get("status")
        formatted_msg["step"] = msg.get("step")
        formatted_msg["progress"] = msg.get("progress")
        formatted_msg["elapsed_seconds"] = msg.get("elapsed_seconds")
      
      formatted_messages.append(formatted_msg)
    
    print(f"[get_chat_messages] Returning {len(formatted_messages)} messages for chat {chat_id}")
    
    return APIResponse(
      code=0,
      msg=f"Retrieved {len(formatted_messages)} messages",
      data={"messages": formatted_messages}
    )
    
  except Exception as e:
    print(f"[get_chat_messages] Error: {e}")
    import traceback
    traceback.print_exc()
    raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {str(e)}")


@router.websocket("/{chat_id}")
async def chat_websocket(websocket: WebSocket, chat_id: str):
  await websocket.accept()
  print(f"[chat_ws] New connection for chat_id={chat_id}")

  # Add to active connections
  if chat_id not in active_connections:
    active_connections[chat_id] = []
  active_connections[chat_id].append(websocket)
  print(f"[chat_ws] Active connections for {chat_id}: {len(active_connections[chat_id])}")

  try:
    while True:
      # Receive message from client
      data = await websocket.receive_json()
      print(f"[chat_ws] Received data: {data}")

      # Get MongoDB collections
      db = get_database()
      messages_collection = db.messages

      # Check message type
      message_type = data.get("type", "user")
      message_content = data.get("content", "").strip()
      
      # Ignore ping messages (used for passive listeners like TripDetail page)
      if message_type == "ping":
        print(f"[chat_ws] Ping received from {data.get('senderId')} in chat {chat_id}")
        continue
      
      # Check if this is a heyAI command
      if message_content.lower().startswith("heyai"):
        # This is a command for the AI
        await handle_heyai_command(
          message_content,
          data.get("senderId"),
          chat_id
        )
        # Don't save as regular message, continue to next iteration
        continue
      
      # Save regular user message to MongoDB
      message_doc = {
        "chatId": chat_id,
        "senderId": data.get("senderId"),
        "senderName": data.get("senderName"),
        "content": message_content,
        "type": "user",
        "createdAt": datetime.utcnow()
      }
      await messages_collection.insert_one(message_doc)
      print(f"[chat_ws] Message saved: {data.get('senderName')} in chat {chat_id}")

      # Broadcast user message to all clients in this chat
      for connection in active_connections[chat_id]:
        await connection.send_json(data)

  except WebSocketDisconnect:
    print(f"[chat_ws] Client disconnected from chat {chat_id}")
    # Remove from active connections
    active_connections[chat_id].remove(websocket)
    if not active_connections[chat_id]:
      del active_connections[chat_id]
      print(f"[chat_ws] No more connections for chat {chat_id}, cleaning up")
  except Exception as e:
    print(f"[chat_ws] Error in WebSocket for chat {chat_id}: {e}")
    import traceback
    traceback.print_exc()
    # Remove from active connections
    if chat_id in active_connections and websocket in active_connections[chat_id]:
      active_connections[chat_id].remove(websocket)
      if not active_connections[chat_id]:
        del active_connections[chat_id]

@router.post("/messages/{message_id}/react")
async def add_reaction(
    message_id: str,
    user_id: str,
    emoji: str = "👍",  # Default to thumbs up
):
    """
    Add or remove reaction to a change request message.
    Used for voting on heyAI change requests.
    """
    try:
        from bson import ObjectId
        
        db = get_database()
        messages_collection = db.messages
        trips_collection = db.trips
        
        # Find the message
        try:
            message = await messages_collection.find_one({"_id": ObjectId(message_id)})
        except:
            raise HTTPException(status_code=400, detail="Invalid message ID")
        
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        if message.get("type") != "change_request":
            raise HTTPException(status_code=400, detail="Can only react to change requests")
        
        # Get change data
        change_data = message.get("change_data", {})
        reactions = change_data.get("reactions", {})
        
        # Toggle reaction (if already reacted, remove it)
        if user_id in reactions:
            del reactions[user_id]
        else:
            reactions[user_id] = emoji
        
        # Count approvals (👍)
        approvals = sum(1 for e in reactions.values() if e == "👍")
        
        # Get trip to calculate majority threshold
        trip_id = message.get("chatId")
        try:
            trip = await trips_collection.find_one({"_id": ObjectId(trip_id)})
        except:
            trip = await trips_collection.find_one({"trip_code": trip_id.upper()})
        
        if not trip:
            raise HTTPException(status_code=404, detail="Trip not found")
        
        total_members = len(trip.get("members", []))
        approvals_needed = (total_members // 2) + 1  # Simple majority
        
        # Update change data
        change_data["reactions"] = reactions
        change_data["approvals_current"] = approvals
        change_data["approvals_needed"] = approvals_needed
        
        # Check if threshold met
        approved = approvals >= approvals_needed
        
        if approved and change_data.get("status") == "pending":
            change_data["status"] = "approved"
        
            # Execute the approved change
            await execute_change_request(
                trip_id,
                change_data["command"],
                change_data["requested_by"]
            )
        
        # Update message in database
        await messages_collection.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": {"change_data": change_data}}
        )
        
        # Broadcast reaction update to all clients
        await broadcast_to_chat(trip_id, {
            "type": "reaction_update",
            "message_id": message_id,
            "reactions": reactions,
            "approvals_current": approvals,
            "approvals_needed": approvals_needed,
            "approved": approved,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {
            "success": True,
            "approvals_current": approvals,
            "approvals_needed": approvals_needed,
            "approved": approved
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[add_reaction] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))