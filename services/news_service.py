import os
import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pymongo import MongoClient
from bson.objectid import ObjectId
from config import get_config


def generate_slug(title: str) -> str:
    """Generate URL-friendly slug from title"""
    slug = title.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    slug = slug.strip('-')
    return slug[:120]  # cap length

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
            slug = generate_slug(title)
            # Ensure slug is unique
            existing = self.blogs_collection.find_one({"slug": slug})
            if existing:
                slug = f"{slug}-{int(datetime.now().timestamp())}"

            blog_post = {
                "title": title,
                "slug": slug,
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

            # Convert datetime to ISO format for JSON response
            if "created_at" in blog_post and blog_post["created_at"]:
                blog_post["created_at"] = blog_post["created_at"].isoformat()
            if "updated_at" in blog_post and blog_post["updated_at"]:
                blog_post["updated_at"] = blog_post["updated_at"].isoformat()

            logger.info(f"Blog post created successfully with ID: {result.inserted_id}, Title: {title}, Type: blog")
            return {
                "success": True,
                "message": "Blog post created successfully",
                "blog": blog_post
            }
            
        except Exception as e:
            logger.error(f"Error creating blog post: {str(e)}")
            return {
                "success": False,
                "message": f"Error creating blog post: {str(e)}"
            }

    def update_blog_post(self, post_id: str, title: str = None, content: str = None,
                        author: str = None, category: str = None, tags: List[str] = None,
                        image_url: str = None, summary: str = None, status: str = None) -> Dict[str, Any]:
        """Update a blog post"""
        try:
            # Build update object with only provided fields
            update_data = {
                "updated_at": datetime.now(timezone.utc)
            }

            if title is not None:
                update_data["title"] = title
                update_data["slug"] = generate_slug(title)
            if content is not None:
                update_data["content"] = content
                # Update summary if content changes
                if summary is None:
                    update_data["summary"] = content[:200] + "..." if len(content) > 200 else content
            if summary is not None:
                update_data["summary"] = summary
            if author is not None:
                update_data["author"] = author
            if category is not None:
                update_data["category"] = category
            if tags is not None:
                update_data["tags"] = tags
            if image_url is not None:
                update_data["image_url"] = image_url
            if status is not None:
                update_data["status"] = status

            result = self.blogs_collection.update_one(
                {"_id": ObjectId(post_id)},
                {"$set": update_data}
            )

            if result.matched_count == 0:
                return {
                    "success": False,
                    "message": "Blog post not found"
                }

            # Fetch updated post
            updated_post = self.blogs_collection.find_one({"_id": ObjectId(post_id)})
            updated_post["_id"] = str(updated_post["_id"])

            logger.info(f"Blog post updated with ID: {post_id}")
            return {
                "success": True,
                "message": "Blog post updated successfully",
                "blog": updated_post
            }

        except Exception as e:
            logger.error(f"Error updating blog post: {str(e)}")
            return {
                "success": False,
                "message": f"Error updating blog post: {str(e)}"
            }

    def delete_post(self, post_id: str, post_type: str = "blog") -> Dict[str, Any]:
        """Delete a post by ID"""
        try:
            collection = self.news_collection if post_type == "news" else self.blogs_collection

            result = collection.delete_one({"_id": ObjectId(post_id)})

            if result.deleted_count == 0:
                return {
                    "success": False,
                    "message": f"{post_type.title()} post not found"
                }

            logger.info(f"{post_type.title()} post deleted with ID: {post_id}")
            return {
                "success": True,
                "message": f"{post_type.title()} post deleted successfully"
            }

        except Exception as e:
            logger.error(f"Error deleting {post_type} post: {str(e)}")
            return {
                "success": False,
                "message": f"Error deleting {post_type} post: {str(e)}"
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
            logger.info(f"Fetching blogs - Query: {query}, Total count: {total_count}, Page: {page}, Limit: {limit}")

            blog_posts = list(self.blogs_collection.find(query)
                            .sort("created_at", -1)
                            .skip(skip)
                            .limit(limit))

            logger.info(f"Found {len(blog_posts)} blog posts")

            # Convert all fields to JSON-serializable format
            serialized_blogs = []
            for post in blog_posts:
                try:
                    serialized_post = {
                        "_id": str(post.get("_id", "")),
                        "slug": post.get("slug", ""),
                        "title": post.get("title", ""),
                        "content": post.get("content", ""),
                        "summary": post.get("summary", ""),
                        "author": post.get("author", ""),
                        "category": post.get("category", "General"),
                        "tags": post.get("tags", []),
                        "imageUrl": post.get("image_url", ""),
                        "status": post.get("status", "published"),
                        "viewCount": post.get("view_count", 0),
                        "likeCount": post.get("like_count", 0),
                        "isFeatured": post.get("is_featured", False),
                        "type": post.get("type", "blog"),
                    }

                    # Handle datetime fields
                    created_at = post.get("created_at")
                    if created_at:
                        if isinstance(created_at, datetime):
                            serialized_post["createdAt"] = created_at.isoformat()
                        else:
                            serialized_post["createdAt"] = str(created_at)
                    else:
                        serialized_post["createdAt"] = ""

                    updated_at = post.get("updated_at")
                    if updated_at:
                        if isinstance(updated_at, datetime):
                            serialized_post["updatedAt"] = updated_at.isoformat()
                        else:
                            serialized_post["updatedAt"] = str(updated_at)
                    else:
                        serialized_post["updatedAt"] = ""

                    serialized_blogs.append(serialized_post)
                except Exception as e:
                    logger.error(f"Error serializing blog post {post.get('_id', 'unknown')}: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue

            logger.info(f"Successfully serialized {len(serialized_blogs)} blogs")

            return {
                "success": True,
                "blogs": serialized_blogs,
                "total": total_count,
                "page": page,
                "limit": limit,
                "totalPages": (total_count + limit - 1) // limit
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

            # Return appropriate key based on post type
            result_key = "blog" if post_type == "blog" else "post"
            return {
                "success": True,
                result_key: post
            }
            
        except Exception as e:
            logger.error(f"Error fetching post: {str(e)}")
            return {
                "success": False,
                "message": f"Error fetching post: {str(e)}"
            }
    
    def get_blog_by_slug(self, slug: str) -> Dict[str, Any]:
        """Get a blog post by its slug"""
        try:
            post = self.blogs_collection.find_one({"slug": slug, "type": "blog"})

            if not post:
                return {"success": False, "message": "Blog not found"}

            post["_id"] = str(post["_id"])

            # Increment view count
            self.blogs_collection.update_one(
                {"slug": slug},
                {"$inc": {"view_count": 1}}
            )

            return {"success": True, "blog": post}

        except Exception as e:
            logger.error(f"Error fetching blog by slug: {str(e)}")
            return {"success": False, "message": f"Error: {str(e)}"}

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