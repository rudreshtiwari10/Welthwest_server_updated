"""
Utility script to ensure all blogs have slug fields
Run this once to fix any existing blogs that don't have slugs
"""

import re
from app import mongo
from bson import ObjectId

def generate_slug(title):
    """Generate URL-friendly slug from title"""
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return slug

def fix_blog_slugs():
    """Add slugs to any blogs that don't have them"""
    blogs_collection = mongo.db['blogs']

    # Find blogs without slug field or with empty slug
    blogs_without_slug = blogs_collection.find({
        '$or': [
            {'slug': {'$exists': False}},
            {'slug': ''},
            {'slug': None}
        ]
    })

    updated_count = 0
    for blog in blogs_without_slug:
        blog_id = blog['_id']
        title = blog.get('title', 'untitled')

        # Generate slug from title
        slug = generate_slug(title)

        # Ensure slug is unique
        existing_slug = blogs_collection.find_one({'slug': slug, '_id': {'$ne': blog_id}})
        if existing_slug:
            # Append _id to make it unique
            slug = f"{slug}-{str(blog_id)[-6:]}"

        # Update blog with slug
        result = blogs_collection.update_one(
            {'_id': blog_id},
            {'$set': {'slug': slug}}
        )

        if result.modified_count > 0:
            updated_count += 1
            print(f"Updated blog '{title}' with slug '{slug}'")

    print(f"\nTotal blogs updated: {updated_count}")

    # List all blogs with their slugs
    print("\n=== All Blogs ===")
    all_blogs = blogs_collection.find({})
    for blog in all_blogs:
        status = blog.get('status', 'unknown')
        print(f"- {blog.get('title')} | slug: {blog.get('slug')} | status: {status}")

if __name__ == '__main__':
    print("Fixing blog slugs...")
    fix_blog_slugs()
    print("Done!")
