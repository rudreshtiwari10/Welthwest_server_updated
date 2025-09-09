# News & Blogs API Documentation

## Overview
The News & Blogs API provides endpoints for managing news articles and blog posts. This API supports CRUD operations, search functionality, and content categorization.

## Base URL
```
http://localhost:5000/api
```

## Authentication
- **Admin Operations** (POST endpoints): Requires JWT token with admin role
- **Read Operations** (GET endpoints): No authentication required

### Headers for Admin Operations
```json
{
  "Content-Type": "application/json",
  "Authorization": "Bearer <your-jwt-token>"
}
```

---

## API Endpoints

### 1. Get All News Posts
**GET** `/news`

Retrieve all news posts with pagination and filtering options.

#### Query Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number for pagination |
| `limit` | integer | 10 | Number of items per page |
| `category` | string | - | Filter by category |
| `featured` | boolean | false | Show only featured posts |

#### Example Request
```bash
curl -X GET "http://localhost:5000/api/news?page=1&limit=5&category=Market News&featured=true"
```

#### Response
```json
{
  "success": true,
  "posts": [
    {
      "_id": "64f8a1b2c3d4e5f6a7b8c9d0",
      "title": "Indian Stock Market Reaches New Heights",
      "content": "The Indian stock market witnessed...",
      "summary": "BSE Sensex crosses 73,000 for the first time...",
      "author": "WelthWest Research Team",
      "category": "Market News",
      "tags": ["Sensex", "Stock Market", "India"],
      "image_url": "https://example.com/image.jpg",
      "created_at": "2024-01-15T10:30:00.000Z",
      "updated_at": "2024-01-15T10:30:00.000Z",
      "status": "published",
      "view_count": 1250,
      "like_count": 45,
      "is_featured": true,
      "type": "news"
    }
  ],
  "total_count": 25,
  "page": 1,
  "limit": 5,
  "total_pages": 5
}
```

---

### 2. Get All Blog Posts
**GET** `/blogs`

Retrieve all blog posts with pagination and filtering options.

#### Query Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number for pagination |
| `limit` | integer | 10 | Number of items per page |
| `category` | string | - | Filter by category |
| `featured` | boolean | false | Show only featured posts |

#### Example Request
```bash
curl -X GET "http://localhost:5000/api/blogs?page=1&limit=10&category=Investment Tips"
```

#### Response Format
Same as news posts with `"type": "blog"`

---

### 3. Get Specific News Post
**GET** `/news/{post_id}`

Retrieve a specific news post by ID. This endpoint automatically increments the view count.

#### Example Request
```bash
curl -X GET "http://localhost:5000/api/news/64f8a1b2c3d4e5f6a7b8c9d0"
```

#### Response
```json
{
  "success": true,
  "post": {
    "_id": "64f8a1b2c3d4e5f6a7b8c9d0",
    "title": "Indian Stock Market Reaches New Heights",
    "content": "The Indian stock market witnessed a historic moment today...",
    "summary": "BSE Sensex crosses 73,000 for the first time...",
    "author": "WelthWest Research Team",
    "category": "Market News",
    "tags": ["Sensex", "Stock Market", "India"],
    "image_url": "https://example.com/image.jpg",
    "created_at": "2024-01-15T10:30:00.000Z",
    "updated_at": "2024-01-15T10:30:00.000Z",
    "status": "published",
    "view_count": 1251,
    "like_count": 45,
    "is_featured": true,
    "type": "news"
  }
}
```

---

### 4. Get Specific Blog Post
**GET** `/blogs/{post_id}`

Retrieve a specific blog post by ID. This endpoint automatically increments the view count.

#### Example Request
```bash
curl -X GET "http://localhost:5000/api/blogs/64f8a1b2c3d4e5f6a7b8c9d1"
```

#### Response Format
Same as news post with `"type": "blog"`

---

### 5. Get Featured Posts
**GET** `/featured-posts`

Retrieve featured posts from both news and blogs, sorted by creation date.

#### Query Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 5 | Maximum number of featured posts |

#### Example Request
```bash
curl -X GET "http://localhost:5000/api/featured-posts?limit=4"
```

#### Response
```json
{
  "success": true,
  "featured_posts": [
    {
      "_id": "64f8a1b2c3d4e5f6a7b8c9d0",
      "title": "Indian Stock Market Reaches New Heights",
      "summary": "BSE Sensex crosses 73,000 for the first time...",
      "author": "WelthWest Research Team",
      "category": "Market News",
      "tags": ["Sensex", "Stock Market"],
      "created_at": "2024-01-15T10:30:00.000Z",
      "view_count": 1251,
      "is_featured": true,
      "type": "news"
    }
  ]
}
```

---

### 6. Search Posts
**GET** `/search-posts`

Search across titles, content, and tags of both news and blog posts.

#### Query Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | Search query |
| `type` | string | No | Filter by type: 'all', 'news', 'blog' (default: 'all') |
| `page` | integer | No | Page number (default: 1) |
| `limit` | integer | No | Items per page (default: 10) |

#### Example Request
```bash
curl -X GET "http://localhost:5000/api/search-posts?q=market%20analysis&type=all&page=1&limit=5"
```

#### Response
```json
{
  "success": true,
  "posts": [
    {
      "_id": "64f8a1b2c3d4e5f6a7b8c9d0",
      "title": "Market Analysis: Understanding P/E Ratios",
      "summary": "A comprehensive guide to P/E ratios...",
      "author": "Arun Patel, CFA",
      "category": "Market Analysis",
      "tags": ["P/E Ratio", "Analysis"],
      "created_at": "2024-01-15T10:30:00.000Z",
      "type": "blog"
    }
  ],
  "total_count": 8,
  "page": 1,
  "limit": 5,
  "total_pages": 2
}
```

---

### 7. Create News Post (Admin Only)
**POST** `/news`

Create a new news article. Requires admin authentication.

#### Request Body
```json
{
  "title": "Market Update: Nifty Hits New High",
  "content": "The Indian stock market witnessed significant gains today as the Nifty 50 index crossed the 21,000 mark for the first time in history...",
  "author": "Market Research Team",
  "category": "Market News",
  "tags": ["Nifty", "Market", "India", "Bulls"],
  "image_url": "https://example.com/market-update.jpg",
  "summary": "Nifty 50 crosses 21,000 mark driven by banking and IT sector gains.",
  "is_featured": true
}
```

#### Field Descriptions
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | Article title |
| `content` | string | Yes | Full article content |
| `author` | string | Yes | Author name |
| `category` | string | No | Category (default: "General") |
| `tags` | array | No | Array of tag strings |
| `image_url` | string | No | URL to featured image |
| `summary` | string | No | Brief summary (auto-generated if not provided) |
| `is_featured` | boolean | No | Mark as featured (default: false) |

#### Categories for News
- General
- Market News  
- Economic Updates
- Technology
- Global Markets

#### Example Request
```bash
curl -X POST "http://localhost:5000/api/news" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d '{
    "title": "Market Update: Nifty Hits New High",
    "content": "The Indian stock market witnessed...",
    "author": "Market Research Team",
    "category": "Market News",
    "tags": ["Nifty", "Market", "India"],
    "is_featured": true
  }'
```

#### Response
```json
{
  "success": true,
  "message": "News post created successfully",
  "post": {
    "_id": "64f8a1b2c3d4e5f6a7b8c9d2",
    "title": "Market Update: Nifty Hits New High",
    "content": "The Indian stock market witnessed...",
    "summary": "Nifty 50 crosses 21,000 mark driven by...",
    "author": "Market Research Team",
    "category": "Market News",
    "tags": ["Nifty", "Market", "India"],
    "created_at": "2024-01-15T14:30:00.000Z",
    "updated_at": "2024-01-15T14:30:00.000Z",
    "status": "published",
    "view_count": 0,
    "like_count": 0,
    "is_featured": true,
    "type": "news"
  }
}
```

---

### 8. Create Blog Post (Admin Only)
**POST** `/blogs`

Create a new blog post. Requires admin authentication.

#### Request Body
```json
{
  "title": "The Future of AI in Finance: Opportunities and Challenges",
  "content": "Artificial Intelligence is revolutionizing the financial services industry, creating unprecedented opportunities while presenting unique challenges...",
  "author": "Dr. Priya Sharma, AI Finance Strategist",
  "category": "AI & Technology",
  "tags": ["AI", "Finance", "Technology", "Future"],
  "image_url": "https://example.com/ai-finance.jpg",
  "summary": "An in-depth analysis of how AI is transforming financial services.",
  "is_featured": false
}
```

#### Categories for Blogs
- Finance
- Investment Tips
- AI & Technology  
- Market Analysis
- Education

#### Example Request
```bash
curl -X POST "http://localhost:5000/api/blogs" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -d '{
    "title": "SIP Investment Guide for Beginners",
    "content": "Systematic Investment Plans (SIPs) have become...",
    "author": "Rajesh Kumar, CFP",
    "category": "Investment Tips",
    "tags": ["SIP", "Investment", "Mutual Funds"],
    "is_featured": true
  }'
```

---

## Error Responses

### Common Error Codes
| Status Code | Description |
|-------------|-------------|
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Invalid or missing token |
| 403 | Forbidden - Admin access required |
| 404 | Not Found - Post doesn't exist |
| 500 | Internal Server Error |

### Error Response Format
```json
{
  "success": false,
  "message": "Error description",
  "error": "Detailed error message"
}
```

### Example Error Responses

#### Invalid Post ID
```json
{
  "success": false,
  "message": "News post not found"
}
```

#### Missing Required Fields
```json
{
  "success": false,
  "message": "title is required"
}
```

#### Admin Access Required
```json
{
  "success": false,
  "message": "Admin access required"
}
```

---

## Data Models

### Post Schema
```json
{
  "_id": "ObjectId",
  "title": "string (required)",
  "content": "string (required)", 
  "summary": "string",
  "author": "string (required)",
  "category": "string",
  "tags": ["string"],
  "image_url": "string",
  "created_at": "Date",
  "updated_at": "Date", 
  "status": "string (default: 'published')",
  "view_count": "number (default: 0)",
  "like_count": "number (default: 0)",
  "is_featured": "boolean (default: false)",
  "type": "string ('news' | 'blog')"
}
```

---

## Usage Examples

### Example 1: Create a Market News Article
```bash
curl -X POST "http://localhost:5000/api/news" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "title": "RBI Maintains Repo Rate at 6.5%: Focus on Inflation",
    "content": "The Reserve Bank of India has decided to maintain the repo rate at 6.5% in its latest monetary policy committee meeting...",
    "author": "Economic Policy Desk",
    "category": "Economic Updates",
    "tags": ["RBI", "Repo Rate", "Monetary Policy", "Inflation"],
    "summary": "RBI maintains repo rate at 6.5% focusing on inflation management.",
    "is_featured": true
  }'
```

### Example 2: Create an Investment Blog
```bash
curl -X POST "http://localhost:5000/api/blogs" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "title": "Building Wealth Through SIPs: A Complete Guide",
    "content": "Systematic Investment Plans (SIPs) have become one of the most popular investment vehicles in India...",
    "author": "Rajesh Kumar, Certified Financial Planner",
    "category": "Investment Tips", 
    "tags": ["SIP", "Mutual Funds", "Investment", "Wealth Creation"],
    "summary": "A comprehensive guide to wealth creation through systematic investing.",
    "is_featured": false
  }'
```

### Example 3: Search for AI-related Content
```bash
curl -X GET "http://localhost:5000/api/search-posts?q=artificial%20intelligence&type=all&limit=5"
```

### Example 4: Get Featured Posts for Homepage
```bash
curl -X GET "http://localhost:5000/api/featured-posts?limit=4"
```

---

## Frontend Integration

The News & Blogs page at `/news-and-blogs` automatically displays content from these APIs:

- **Main Page**: Shows all posts with search, filtering, and pagination
- **Detail Pages**: `/news/{id}` and `/blog/{id}` show full articles  
- **Featured Section**: Highlights important content
- **Related Posts**: Shows similar content based on category

### Sample Frontend Usage
```javascript
// Fetch news for display
const response = await fetch('/api/news?page=1&limit=10&featured=true');
const data = await response.json();

// Display posts
data.posts.forEach(post => {
  console.log(`${post.title} by ${post.author}`);
});
```

---

## Notes

1. **Auto-generated Fields**: `created_at`, `updated_at`, `view_count`, `like_count` are automatically managed
2. **Content Formatting**: Support for markdown-style formatting in content
3. **Image URLs**: Should be valid, publicly accessible URLs
4. **Categories**: Use predefined categories for consistency
5. **Tags**: Use relevant, lowercase tags for better searchability
6. **Featured Posts**: Limit featured posts to maintain quality
7. **Content Length**: No strict limits, but consider readability
8. **SEO**: Include relevant keywords in title, summary, and tags

---

## Testing

Use the provided sample data script to populate initial content:

```bash
cd WelthWestServer2
python populate_news.py
```

This will create sample news articles and blog posts for testing the API endpoints.