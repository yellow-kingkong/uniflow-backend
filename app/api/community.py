from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.database import get_db
from app.models import LoungePost, User, CommunityComment
from pydantic import BaseModel

router = APIRouter(tags=["community"])

# --- Schemas ---

class PostCreate(BaseModel):
    user_id: str
    title: str
    content: str
    category: str # lounge, sos, insight

class CommentCreate(BaseModel):
    post_id: str
    user_id: str
    content: str

# --- Endpoints ---

@router.get("/posts")
def list_posts(category: Optional[str] = None, db: Session = Depends(get_db)):
    """커뮤니티 게시글 목록 조회"""
    query = db.query(LoungePost).filter(LoungePost.is_hidden == False)
    if category and category.lower() != "all":
        query = query.filter(LoungePost.category == category)
    
    posts = query.order_by(LoungePost.created_at.desc()).all()
    
    result = []
    for post in posts:
        user = db.query(User).filter(User.id == post.user_id).first()
        comment_count = db.query(CommunityComment).filter(CommunityComment.post_id == post.id).count()
        result.append({
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "category": post.category,
            "author": user.name if user else "Unknown",
            "created_at": post.created_at,
            "view_count": post.view_count,
            "comment_count": comment_count,
            "report_count": post.report_count
        })
    return result

@router.get("/posts/{post_id}")
def get_post_detail(post_id: str, db: Session = Depends(get_db)):
    """게시글 상세 조회 (조회수 증가)"""
    post = db.query(LoungePost).filter(LoungePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
        
    post.view_count += 1
    db.commit()
    
    user = db.query(User).filter(User.id == post.user_id).first()
    comments = db.query(CommunityComment).filter(CommunityComment.post_id == post_id).all()
    
    return {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "category": post.category,
        "author": user.name if user else "Unknown",
        "created_at": post.created_at,
        "view_count": post.view_count,
        "comments": [
            {
                "id": c.id,
                "author": db.query(User.name).filter(User.id == c.user_id).scalar() or "Unknown",
                "content": c.content,
                "created_at": c.created_at
            } for c in comments
        ]
    }

@router.post("/posts")
def create_post(req: PostCreate, db: Session = Depends(get_db)):
    """새 게시글 작성"""
    new_post = LoungePost(
        id=str(uuid.uuid4()),
        user_id=req.user_id,
        title=req.title,
        content=req.content,
        category=req.category
    )
    db.add(new_post)
    db.commit()
    return {"message": "Post created successfully"}

@router.post("/posts/{post_id}/report")
def report_post(post_id: str, db: Session = Depends(get_db)):
    """게시글 신고"""
    post = db.query(LoungePost).filter(LoungePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    post.report_count += 1
    if post.report_count >= 5:
        post.is_hidden = True # 5번 이상 신고 시 자동 숨김
    
    db.commit()
    return {"message": "Reported successfully"}

@router.put("/posts/{post_id}")
def update_post(post_id: str, req: PostCreate, db: Session = Depends(get_db)):
    """게시글 수정"""
    post = db.query(LoungePost).filter(LoungePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    post.title = req.title
    post.content = req.content
    post.category = req.category
    
    db.commit()
    return {"message": "Updated successfully"}

@router.delete("/posts/{post_id}")
def delete_post(post_id: str, db: Session = Depends(get_db)):
    """게시글 삭제"""
    post = db.query(LoungePost).filter(LoungePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    db.delete(post)
    db.commit()
    return {"message": "Deleted successfully"}

# --- 댓글 (Comments) ---

@router.post("/comments")
def create_comment(req: CommentCreate, db: Session = Depends(get_db)):
    """댓글 작성"""
    new_comment = CommunityComment(
        id=str(uuid.uuid4()),
        post_id=req.post_id,
        user_id=req.user_id,
        content=req.content
    )
    db.add(new_comment)
    db.commit()
    return {"message": "Comment created successfully"}

@router.delete("/comments/{comment_id}")
def delete_comment(comment_id: str, db: Session = Depends(get_db)):
    """댓글 삭제"""
    comment = db.query(CommunityComment).filter(CommunityComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
        
    db.delete(comment)
    db.commit()
    return {"message": "Deleted successfully"}
