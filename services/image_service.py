"""
Article Image Service
Sources images for articles: cluster source images -> Gemini Imagen -> None
Uploads to Cloudinary for self-hosted SEO-friendly URLs
"""

import os
import io
import base64
import logging
import hashlib
import requests
from typing import Optional, List

logger = logging.getLogger(__name__)

CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY', '')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')


class ImageService:
    """Handles article image sourcing and Cloudinary upload"""

    # ── Cloudinary Upload ─────────────────────────────────────

    @staticmethod
    def _configure_cloudinary():
        import cloudinary
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
        )

    @staticmethod
    def _cloudinary_configured() -> bool:
        return all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET])

    def upload_to_cloudinary(self, source, public_id: str) -> Optional[str]:
        """
        Upload image to Cloudinary. Source can be a URL string or bytes/BytesIO.
        Returns the optimized Cloudinary URL with 1200x630 crop.
        """
        if not self._cloudinary_configured():
            logger.warning("Cloudinary not configured — skipping upload")
            return None

        try:
            self._configure_cloudinary()
            import cloudinary.uploader

            result = cloudinary.uploader.upload(
                source,
                public_id=f"welthwest/articles/{public_id}",
                overwrite=True,
                resource_type="image",
                transformation=[
                    {"width": 1200, "height": 630, "crop": "fill", "gravity": "auto"},
                    {"quality": "auto", "fetch_format": "auto"},
                ],
            )

            url = result.get('secure_url')
            logger.info(f"Uploaded to Cloudinary: {url}")
            return url

        except Exception as e:
            logger.error(f"Cloudinary upload failed: {e}")
            return None

    # ── Source 1: Cluster Images ──────────────────────────────

    @staticmethod
    def get_image_from_cluster(cluster: List[dict]) -> Optional[str]:
        """Extract best usable image URL from source news items"""
        for item in cluster:
            image_url = (
                item.get('image_url')
                or item.get('imageUrl')
                or item.get('urlToImage')
            )
            if not image_url or not image_url.startswith('http'):
                continue

            # Validate URL is reachable and actually an image
            try:
                resp = requests.head(image_url, timeout=5, allow_redirects=True)
                content_type = resp.headers.get('content-type', '')
                if resp.status_code == 200 and 'image' in content_type:
                    logger.info(f"Found cluster image: {image_url[:80]}")
                    return image_url
            except Exception:
                continue

        return None

    # ── Source 2: Gemini Imagen ────────────────────────────────

    @staticmethod
    def generate_image_gemini(title: str, sector: str, sentiment: str) -> Optional[bytes]:
        """Generate an article banner image using Gemini's image generation"""
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set — skipping image generation")
            return None

        prompt = (
            f"Create a professional, photorealistic 16:9 banner image for a financial news article. "
            f"Topic: {title}. Sector: {sector}. Market sentiment: {sentiment}. "
            f"Requirements: professional financial/business aesthetic, clean modern look "
            f"suitable for a news website header, no text or watermarks in the image, "
            f"relevant visual metaphor for the topic, rich colors and high contrast."
        )

        # Try Imagen 3 first
        image_bytes = ImageService._try_imagen3(prompt)
        if image_bytes:
            return image_bytes

        # Fallback: Gemini Flash with image generation
        image_bytes = ImageService._try_gemini_flash_image(prompt)
        if image_bytes:
            return image_bytes

        return None

    @staticmethod
    def _try_imagen3(prompt: str) -> Optional[bytes]:
        """Try Google Imagen 3 model"""
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"imagen-3.0-generate-002:predict?key={GEMINI_API_KEY}"
            )
            payload = {
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": "16:9",
                    "safetyFilterLevel": "block_only_high",
                },
            }

            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code != 200:
                logger.info(f"Imagen 3 returned {resp.status_code}, skipping")
                return None

            predictions = resp.json().get('predictions', [])
            if predictions:
                b64 = predictions[0].get('bytesBase64Encoded')
                if b64:
                    logger.info("Generated image via Imagen 3")
                    return base64.b64decode(b64)

        except Exception as e:
            logger.warning(f"Imagen 3 error: {e}")

        return None

    @staticmethod
    def _try_gemini_flash_image(prompt: str) -> Optional[bytes]:
        """Try Gemini Flash with image generation capability"""
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash-preview-image-generation:generateContent?key={GEMINI_API_KEY}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                },
            }

            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code != 200:
                logger.info(f"Gemini Flash image gen returned {resp.status_code}")
                return None

            candidates = resp.json().get('candidates', [])
            if candidates:
                parts = candidates[0].get('content', {}).get('parts', [])
                for part in parts:
                    inline = part.get('inlineData')
                    if inline and inline.get('data'):
                        logger.info("Generated image via Gemini Flash")
                        return base64.b64decode(inline['data'])

        except Exception as e:
            logger.warning(f"Gemini Flash image gen error: {e}")

        return None

    # ── Main Orchestrator ─────────────────────────────────────

    def get_article_image(self, cluster: List[dict], article_data: dict) -> Optional[str]:
        """
        Get an image for the article. Returns Cloudinary URL or None.
        Priority: cluster source image -> Gemini generated -> None
        """
        title = article_data.get('title', 'untitled')
        slug = article_data.get('slug', title)
        public_id = hashlib.md5(slug.encode()).hexdigest()[:12]

        # Source 1: cluster images (download from source, re-host on Cloudinary)
        source_url = self.get_image_from_cluster(cluster)
        if source_url:
            cloudinary_url = self.upload_to_cloudinary(source_url, public_id)
            if cloudinary_url:
                return cloudinary_url
            # If Cloudinary upload failed, don't use the raw external URL (bad for SEO)

        # Source 2: AI-generated image
        sector = article_data.get('sector', 'General')
        sentiment = article_data.get('sentiment', 'Neutral')
        image_bytes = self.generate_image_gemini(title, sector, sentiment)
        if image_bytes:
            cloudinary_url = self.upload_to_cloudinary(io.BytesIO(image_bytes), public_id)
            if cloudinary_url:
                return cloudinary_url

        logger.info(f"No image sourced for: {title[:60]}")
        return None
