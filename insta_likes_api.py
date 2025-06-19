from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from instagrapi import Client
from typing import Optional
import logging

# Simple logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Simple Instagram API")

# Request/Response models
class PostRequest(BaseModel):
    shortcode: str

class LikesResponse(BaseModel):
    shortcode: str
    likes_count: int
    comments_count: int
    views_count: Optional[int] = None
    caption: Optional[str] = None

# Instagram credentials - replace with your actual credentials
USERNAME = "beet3531"
PASSWORD = "susguy69"

# Global client instance
cl = Client()

@app.on_event("startup")
async def startup_event():
    """Login to Instagram on startup"""
    try:
        cl.login(USERNAME, PASSWORD)
        logger.info("Successfully logged in to Instagram")
    except Exception as e:
        logger.error(f"Failed to login: {e}")

@app.get("/")
async def root():
    return {
        "message": "Simple Instagram API",
        "endpoints": {
            "GET /get_likes?shortcode=SHORTCODE": "Get likes for a post",
            "POST /get_likes": "Get likes for a post (JSON body)"
        }
    }

@app.get("/get_likes", response_model=LikesResponse)
async def get_post_likes_get(shortcode: str):
    """Get Instagram post data using shortcode (GET request)"""
    try:
        # Get media info
        media_pk = cl.media_pk_from_code(shortcode)
        media_info = cl.media_info(media_pk)
        
        # Extract data
        likes_count = media_info.like_count or 0
        comments_count = media_info.comment_count or 0
        views_count = getattr(media_info, 'view_count', 0) or 0
        caption = getattr(media_info, 'caption_text', None)
        
        logger.info(f"Retrieved data for {shortcode}: {likes_count} likes, {comments_count} comments")
        
        return LikesResponse(
            shortcode=shortcode,
            likes_count=likes_count,
            comments_count=comments_count,
            views_count=views_count,
            caption=caption
        )
        
    except Exception as e:
        logger.error(f"Error fetching data for {shortcode}: {e}")
        raise HTTPException(status_code=400, detail=f"Error fetching post data: {str(e)}")

@app.post("/get_likes", response_model=LikesResponse)
async def get_post_likes_post(request: PostRequest):
    """Get Instagram post data using shortcode (POST request)"""
    try:
        # Get media info
        media_pk = cl.media_pk_from_code(request.shortcode)
        media_info = cl.media_info(media_pk)
        
        # Extract data
        likes_count = media_info.like_count or 0
        comments_count = media_info.comment_count or 0
        views_count = getattr(media_info, 'view_count', 0) or 0
        caption = getattr(media_info, 'caption_text', None)
        
        logger.info(f"Retrieved data for {request.shortcode}: {likes_count} likes, {comments_count} comments")
        
        return LikesResponse(
            shortcode=request.shortcode,
            likes_count=likes_count,
            comments_count=comments_count,
            views_count=views_count,
            caption=caption
        )
        
    except Exception as e:
        logger.error(f"Error fetching data for {request.shortcode}: {e}")
        raise HTTPException(status_code=400, detail=f"Error fetching post data: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
