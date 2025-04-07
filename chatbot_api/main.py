"""Main entrypoint for the app.

This module contains the main application logic for the chatbot API.
It sets up the FastAPI application, configures middleware, and defines the API routes.
"""

import os
import asyncio
from typing import Optional, Union
from uuid import UUID

import langsmith
from chatbot_api.chains import ChatRequest, answer_chain
from chatbot_api.chains.session import SessionManager
from fastapi import FastAPI, Form, Response, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langserve import add_routes
from langsmith import Client
from pydantic import BaseModel
from twilio.twiml.messaging_response import MessagingResponse
import requests


# Initialize the LangSmith client
client = Client()

# Initialize the FastAPI application
app = FastAPI()

# Initialize the session manager
session_manager = SessionManager()

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_HOSTS", "*",)],
    allow_credentials=True,
    allow_methods=[os.getenv("ALLOWED_HOSTS", "*",)],
    allow_headers=[os.getenv("ALLOWED_HOSTS", "*",)],
    expose_headers=[os.getenv("ALLOWED_HOSTS", "*",)],
)

@app.post("/webhook")
async def chat(From: str = Form(...), Body: str = Form(...)):
    """
    Handles incoming chat messages via the webhook.

    This endpoint receives messages from users, processes them using the answer_chain,
    and returns a response in Twilio's TwiML format to be sent back to the user.

    Args:
        From (str): The phone number of the sender.
        Body (str): The body of the incoming message.

    Returns:
        Response: A FastAPI Response object containing the TwiML response.
    """
    # Create a session ID based on the phone number
    session_id = f"twilio_{From}"
    
    # Get or create session
    session = session_manager.get_session(session_id)
    if not session:
        session_manager.create_session(session_id)
        session = session_manager.get_session(session_id)
    
    # Get chat history from session
    chat_history = session.get_history()
    
    # Process the request using the answer chain
    ans = answer_chain.invoke({'question': Body, 'chat_history': chat_history})
    
    # Update session history
    session.add_message('human', Body)
    session.add_message('ai', ans)
    
    response = MessagingResponse()
    msg = response.message(f"{ans}")
    return Response(content=str(response), media_type="application/xml")

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    """
    Handles incoming messages from Telegram.
    
    This endpoint receives updates from Telegram, processes them using the answer_chain,
    and sends the response back to the user via Telegram's API.
    
    Args:
        request (Request): The incoming request from Telegram containing the update.
    
    Returns:
        dict: A response indicating success.
    """
    update = await request.json()
    
    # Extract message data from the update
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        message_text = update["message"]["text"]
        
        # Create a session ID based on the chat ID
        session_id = f"telegram_{chat_id}"
        
        # Get or create session
        session = session_manager.get_session(session_id)
        if not session:
            session_manager.create_session(session_id)
            session = session_manager.get_session(session_id)
        
        # Get chat history from session
        chat_history = session.get_history()
        
        # Process the message using our existing chain
        ans = answer_chain.invoke({'question': message_text, 'chat_history': chat_history})
        
        # Update session history
        session.add_message('human', message_text)
        session.add_message('ai', ans)
        
        # Send the response back to Telegram
        # Get the Telegram bot token from environment variables
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        
        if not bot_token:
            return {"status": "error", "message": "Telegram bot token not configured"}
        
        # Send the response back to the user
        telegram_api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": ans,
            "parse_mode": "HTML"  # Allow HTML formatting in the response
        }
        
        response = requests.post(telegram_api_url, json=payload)
        
        if response.status_code == 200:
            return {"status": "success", "message": "Response sent to user"}
        else:
            return {"status": "error", "message": f"Failed to send response: {response.text}"}
    
    return {"status": "no message to process"}

# Add routes to the application
add_routes(
    app,
    answer_chain,
    path="/chat",
    input_type=ChatRequest,
    config_keys=["metadata", "configurable", "tags"],
)

# Custom chat endpoint with session management
@app.post("/chat-with-history")
async def chat_with_history(request: ChatRequest):
    """Handle chat requests with session management."""
    # Create or get session
    if not request.session_id:
        request.session_id = session_manager.create_session()
    
    session = session_manager.get_session(request.session_id)
    if not session:
        session = session_manager.create_session(request.session_id)
    
    # Get chat history from session
    request.chat_history = session.get_history()
    
    # Process the request using the answer chain
    response = answer_chain.invoke({
        'question': request.question,
        'chat_history': request.chat_history
    })
    
    # Update session history
    session.add_message('human', request.question)
    session.add_message('ai', response)
    
    return {
        'answer': response,
        'session_id': request.session_id
    }

@app.delete("/chat/{session_id}")
async def clear_chat_history(session_id: str):
    """Clear chat history for a session."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_manager.delete_session(session_id)
    return {"status": "success", "message": "Chat history cleared"}

class SendFeedbackBody(BaseModel):
    """Model for the body of the send feedback request."""
    run_id: UUID
    key: str = "user_score"
    score: Union[float, int, bool, None] = None
    feedback_id: Optional[UUID] = None
    comment: Optional[str] = None

@app.post("/feedback")
async def send_feedback(body: SendFeedbackBody):
    """Endpoint to send feedback.

    This endpoint accepts a POST request with a body containing feedback information.
    It uses the LangSmith client to create a feedback entry.

    Args:
        body (SendFeedbackBody): The body of the request, containing feedback information.

    Returns:
        dict: A dictionary with the result of the operation and the HTTP status code.
    """
    client.create_feedback(
        body.run_id,
        body.key,
        score=body.score,
        comment=body.comment,
        feedback_id=body.feedback_id,
    )
    return {"result": "posted feedback successfully", "code": 200}

class UpdateFeedbackBody(BaseModel):
    """Model for the body of the update feedback request."""
    feedback_id: UUID
    score: Union[float, int, bool, None] = None
    comment: Optional[str] = None

@app.patch("/feedback")
async def update_feedback(body: UpdateFeedbackBody):
    """Endpoint to update feedback.

    This endpoint accepts a PATCH request with a body containing updated feedback information.
    It uses the LangSmith client to update a feedback entry.

    Args:
        body (UpdateFeedbackBody): The body of the request, containing updated feedback information.

    Returns:
        dict: A dictionary with the result of the operation and the HTTP status code.
    """
    feedback_id = body.feedback_id
    if feedback_id is None:
        return {
            "result": "No feedback ID provided",
            "code": 400,
        }
    client.update_feedback(
        feedback_id,
        score=body.score,
        comment=body.comment,
    )
    return {"result": "patched feedback successfully", "code": 200}

async def _arun(func, *args, **kwargs):
    """Helper function to run a function in the executor of the current event loop.

    Args:
        func (callable): The function to run.
        *args: Positional arguments to pass to the function.
        **kwargs: Keyword arguments to pass to the function.

    Returns:
        The result of the function call.
    """
    return await asyncio.get_running_loop().run_in_executor(None, func, *args, **kwargs)

async def aget_trace_url(run_id: str) -> str:
    """Get the trace URL for a given run ID.

    This function attempts to read the run and share it if it's not already shared.
    It retries up to 5 times in case of a LangSmithError.

    Args:
        run_id (str): The run ID to get the trace URL for.

    Returns:
        str: The trace URL for the run.
    """
    for i in range(5):
        try:
            await _arun(client.read_run, run_id)
            break
        except langsmith.utils.LangSmithError:
            await asyncio.sleep(1**i)

    if await _arun(client.run_is_shared, run_id):
        return await _arun(client.read_run_shared_link, run_id)
    return await _arun(client.share_run, run_id)

class GetTraceBody(BaseModel):
    """Model for the body of the get trace request."""
    run_id: UUID

@app.post("/get_trace")
async def get_trace(body: GetTraceBody):
    """Endpoint to get the trace for a given run ID.

    This endpoint accepts a POST request with a body containing a run ID.
    It returns the trace URL for the run.

    Args:
        body (GetTraceBody): The body of the request, containing the run ID.

    Returns:
        str: The trace URL for the run.
    """
    run_id = body.run_id
    if run_id is None:
        return {
            "result": "No LangSmith run ID provided",
            "code": 400,
        }
    return await aget_trace_url(str(run_id))

if __name__ == "__main__":
    """Main execution point of the application.

    This block is executed when the module is run directly, not when it is imported.
    It starts the FastAPI application using uvicorn.
    """
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
