from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import instaloader
from typing import Optional

app = FastAPI(title="Instagram Post Likes API")

class PostRequest(BaseModel):
    shortcode: str

class LikesResponse(BaseModel):
    shortcode: str
    likes_count: int
    comments_count: int
    views_count: Optional[int] = None
    caption: Optional[str] = None
    error: Optional[str] = None

@app.post("/get_likes", response_model=LikesResponse)
async def get_post_likes(request: PostRequest):
    try:
        # Initialize Instaloader
        L = instaloader.Instaloader()
        
        # Get post from shortcode
        post = instaloader.Post.from_shortcode(L.context, request.shortcode)
        
        
        # Get likes count
        likes_count = post.likes
        comments_count = post.comments
        views_count = post.video_view_count if post.is_video else 0
        if not likes_count:
            raise HTTPException(status_code=404, detail="Post not found or has no likes.")
        
        # Get caption (optional)
        caption = post.caption if post.caption else None
        
        return LikesResponse(
            shortcode=request.shortcode,
            likes_count=likes_count,
            comments_count=comments_count,
            views_count=views_count
        )
    
    except instaloader.exceptions.InstaloaderException as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error fetching post data: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/")
async def root():
    return {"message": "Welcome to Instagram Post Likes API. Use POST /get_likes with a shortcode."}