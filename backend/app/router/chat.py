from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import GOOGLE_AI_API_KEY, GOOGLE_AI_MODEL, JWT_ALGORITHM, JWT_SECRET
from app.models.common import APIResponse

router = APIRouter(prefix="/chat", tags=["Chat"])
security = HTTPBearer()


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = []


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Extract user ID from JWT token."""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user ID")
        return user_id
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")


@router.post("/", response_model=APIResponse)
async def chat(request: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """
    Chat endpoint for AI travel planning assistant.
    
    Uses Google Gemini to provide conversational assistance for travel planning.
    """
    if not GOOGLE_AI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured. Please set GOOGLE_AI_API_KEY environment variable.",
        )

    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(model=GOOGLE_AI_MODEL, temperature=0.7, api_key=GOOGLE_AI_API_KEY)

        # Build conversation context
        system_prompt = """You are a helpful AI travel planning assistant for a group travel planning application. 
Your role is to help users plan their trips by:
- Answering questions about travel destinations, activities, and planning
- Providing suggestions for group travel
- Helping with itinerary planning
- Answering questions about preferences, budgets, and travel logistics
- Being friendly, informative, and concise

Keep your responses conversational and helpful. If you don't know something, admit it rather than making things up."""

        # Format conversation history using LangChain message types
        messages = [SystemMessage(content=system_prompt)]
        
        # Add history (limit to last 10 messages to avoid token limits)
        recent_history = request.history[-10:] if len(request.history) > 10 else request.history
        for msg in recent_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))
        
        # Add current message
        messages.append(HumanMessage(content=request.message))

        # Get response from LLM
        response = llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)

        return APIResponse(
            code=0,
            msg="ok",
            data={"message": response_text},
        )

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="AI service dependencies are not installed. Please install langchain-google-genai.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process chat message: {str(e)}",
        )

