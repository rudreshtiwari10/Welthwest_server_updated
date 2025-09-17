import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pymongo import MongoClient
from bson.objectid import ObjectId
from config import get_config

logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Connect to MongoDB using connection string from environment variable
    """
    config = get_config()
    mongo_uri = os.environ.get('MONGODB_URI', 'mongodb://localhost:27017')
    
    try:
        client = MongoClient(mongo_uri)
        db = client.get_database(config.DB_NAME)
        return db
    except Exception as e:
        logger.error(f"MongoDB connection error: {str(e)}")
        client = MongoClient('mongodb://localhost:27017')
        db = client.get_database(config.DB_NAME)
        return db

class NewsService:
    """Service for managing news and blog posts"""
    
    def __init__(self):
        self.db = get_db_connection()
        self.news_collection = self.db.news_posts
        self.blogs_collection = self.db.blog_posts
    
    def create_news_post(self, title: str, content: str, author: str, 
                        category: str = "General", tags: List[str] = None, 
                        image_url: str = None, summary: str = None) -> Dict[str, Any]:
        """Create a new news post"""
        try:
            news_post = {
                "title": title,
                "content": content,
                "summary": summary or content[:200] + "..." if len(content) > 200 else content,
                "author": author,
                "category": category,
                "tags": tags or [],
                "image_url": image_url,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "status": "published",
                "view_count": 0,
                "like_count": 0,
                "is_featured": False,
                "type": "news"
            }
            
            result = self.news_collection.insert_one(news_post)
            news_post["_id"] = str(result.inserted_id)
            
            logger.info(f"News post created with ID: {result.inserted_id}")
            return {
                "success": True,
                "message": "News post created successfully",
                "post": news_post
            }
            
        except Exception as e:
            logger.error(f"Error creating news post: {str(e)}")
            return {
                "success": False,
                "message": f"Error creating news post: {str(e)}"
            }
    
    def create_blog_post(self, title: str, content: str, author: str, 
                        category: str = "Finance", tags: List[str] = None, 
                        image_url: str = None, summary: str = None) -> Dict[str, Any]:
        """Create a new blog post"""
        try:
            blog_post = {
                "title": title,
                "content": content,
                "summary": summary or content[:200] + "..." if len(content) > 200 else content,
                "author": author,
                "category": category,
                "tags": tags or [],
                "image_url": image_url,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "status": "published",
                "view_count": 0,
                "like_count": 0,
                "is_featured": False,
                "type": "blog"
            }
            
            result = self.blogs_collection.insert_one(blog_post)
            blog_post["_id"] = str(result.inserted_id)
            
            logger.info(f"Blog post created with ID: {result.inserted_id}")
            return {
                "success": True,
                "message": "Blog post created successfully",
                "post": blog_post
            }
            
        except Exception as e:
            logger.error(f"Error creating blog post: {str(e)}")
            return {
                "success": False,
                "message": f"Error creating blog post: {str(e)}"
            }
    
    def get_all_news(self, page: int = 1, limit: int = 10, 
                     category: str = None, featured_only: bool = False) -> Dict[str, Any]:
        """Get all news posts with pagination and filtering"""
        try:
            query = {"type": "news"}
            if category:
                query["category"] = category
            if featured_only:
                query["is_featured"] = True
            
            skip = (page - 1) * limit
            
            total_count = self.news_collection.count_documents(query)
            
            news_posts = list(self.news_collection.find(query)
                            .sort("created_at", -1)
                            .skip(skip)
                            .limit(limit))
            
            # Convert ObjectId to string for JSON serialization
            for post in news_posts:
                post["_id"] = str(post["_id"])
            
            return {
                "success": True,
                "posts": news_posts,
                "total_count": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit
            }
            
        except Exception as e:
            logger.error(f"Error fetching news posts: {str(e)}")
            return {
                "success": False,
                "message": f"Error fetching news posts: {str(e)}"
            }
    
    def get_all_blogs(self, page: int = 1, limit: int = 10, 
                      category: str = None, featured_only: bool = False) -> Dict[str, Any]:
        """Get all blog posts with pagination and filtering"""
        try:
            query = {"type": "blog"}
            if category:
                query["category"] = category
            if featured_only:
                query["is_featured"] = True
            
            skip = (page - 1) * limit
            
            total_count = self.blogs_collection.count_documents(query)
            
            blog_posts = list(self.blogs_collection.find(query)
                            .sort("created_at", -1)
                            .skip(skip)
                            .limit(limit))
            
            # Convert ObjectId to string for JSON serialization
            for post in blog_posts:
                post["_id"] = str(post["_id"])
            
            return {
                "success": True,
                "posts": blog_posts,
                "total_count": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit
            }
            
        except Exception as e:
            logger.error(f"Error fetching blog posts: {str(e)}")
            return {
                "success": False,
                "message": f"Error fetching blog posts: {str(e)}"
            }
    
    def get_post_by_id(self, post_id: str, post_type: str = "news") -> Dict[str, Any]:
        """Get a specific post by ID"""
        try:
            collection = self.news_collection if post_type == "news" else self.blogs_collection
            post = collection.find_one({"_id": ObjectId(post_id)})
            
            if not post:
                return {
                    "success": False,
                    "message": f"{post_type.title()} post not found"
                }
            
            post["_id"] = str(post["_id"])
            
            # Increment view count
            collection.update_one(
                {"_id": ObjectId(post_id)},
                {"$inc": {"view_count": 1}}
            )
            
            return {
                "success": True,
                "post": post
            }
            
        except Exception as e:
            logger.error(f"Error fetching post: {str(e)}")
            return {
                "success": False,
                "message": f"Error fetching post: {str(e)}"
            }
    
    def get_featured_posts(self, limit: int = 5) -> Dict[str, Any]:
        """Get featured posts from both news and blogs"""

        try:
            featured_news = list(self.news_collection.find({"is_featured": True})
                                .sort("created_at", -1)
                                .limit(limit // 2))
            
            featured_blogs = list(self.blogs_collection.find({"is_featured": True})
                                .sort("created_at", -1)
                                .limit(limit // 2))
            
            # Convert ObjectId to string
            for post in featured_news + featured_blogs:
                post["_id"] = str(post["_id"])
            
            # Combine and sort by created_at
            all_featured = featured_news + featured_blogs
            all_featured.sort(key=lambda x: x["created_at"], reverse=True)
            
            return {
                "success": True,
                "featured_posts": all_featured[:limit]
            }
            
        except Exception as e:
            logger.error(f"Error fetching featured posts: {str(e)}")
            return {
                "success": False,
                "message": f"Error fetching featured posts: {str(e)}"
            }
    
    def search_posts(self, query: str, post_type: str = "all", page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """Search posts by title, content, or tags"""
        try:
            search_regex = {"$regex": query, "$options": "i"}
            search_query = {
                "$or": [
                    {"title": search_regex},
                    {"content": search_regex},
                    {"tags": search_regex}
                ]
            }
            
            results = []
            total_count = 0
            
            if post_type in ["all", "news"]:
                news_results = list(self.news_collection.find(search_query)
                                  .sort("created_at", -1))
                results.extend(news_results)
            
            if post_type in ["all", "blog"]:
                blog_results = list(self.blogs_collection.find(search_query)
                                  .sort("created_at", -1))
                results.extend(blog_results)
            
            # Sort combined results by created_at
            results.sort(key=lambda x: x["created_at"], reverse=True)
            
            total_count = len(results)
            skip = (page - 1) * limit
            paginated_results = results[skip:skip + limit]
            
            # Convert ObjectId to string
            for post in paginated_results:
                post["_id"] = str(post["_id"])
            
            return {
                "success": True,
                "posts": paginated_results,
                "total_count": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit
            }
            
        except Exception as e:
            logger.error(f"Error searching posts: {str(e)}")
            return {
                "success": False,
                "message": f"Error searching posts: {str(e)}"
            }

# Create singleton instance
news_service = NewsService()