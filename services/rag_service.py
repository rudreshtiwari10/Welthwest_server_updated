"""
RAG (Retrieval-Augmented Generation) Service for Financial Documents

Enables AI to analyze financial documents (PDFs):
- Earnings reports
- Annual reports (10-K, annual reports)
- Investor presentations
- Prospectus documents
- Financial statements

Features:
- PDF text extraction
- Document chunking with overlap
- Semantic embedding using sentence-transformers
- Vector storage using ChromaDB (lightweight)
- Semantic search and retrieval
- Context assembly for LLM

Uses lightweight models suitable for small servers
"""

import os
import logging
from typing import Dict, Any, List, Optional
import hashlib
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Optional imports with graceful degradation
HAS_PDF_SUPPORT = False
HAS_EMBEDDINGS = False
HAS_CHROMADB = False

try:
    import PyPDF2
    HAS_PDF_SUPPORT = True
except ImportError:
    logger.warning("PyPDF2 not installed. PDF extraction will not be available.")

try:
    from sentence_transformers import SentenceTransformer
    HAS_EMBEDDINGS = True
except ImportError:
    logger.warning("sentence-transformers not installed. Embeddings will not be available.")

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    logger.warning("chromadb not installed. Vector storage will not be available.")


class RAGService:
    """
    RAG service for financial document analysis
    """

    def __init__(self, data_dir: str = "./rag_data"):
        """
        Initialize RAG service

        Args:
            data_dir: Directory to store document data and embeddings
        """
        self.data_dir = data_dir
        self.embeddings_model = None
        self.chroma_client = None
        self.collection = None

        # Create data directory
        os.makedirs(data_dir, exist_ok=True)

        # Check if all dependencies are available
        if not HAS_PDF_SUPPORT:
            logger.error("PDF support not available. Install PyPDF2: pip install PyPDF2")
        if not HAS_EMBEDDINGS:
            logger.error("Embeddings not available. Install sentence-transformers: pip install sentence-transformers")
        if not HAS_CHROMADB:
            logger.error("Vector DB not available. Install chromadb: pip install chromadb")

        # Initialize components if available
        if HAS_EMBEDDINGS:
            try:
                # Use lightweight model for embeddings
                self.embeddings_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Loaded embedding model: all-MiniLM-L6-v2")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")

        if HAS_CHROMADB:
            try:
                # Initialize ChromaDB with persistent storage
                self.chroma_client = chromadb.PersistentClient(
                    path=os.path.join(data_dir, "chroma_db")
                )
                # Create or get collection
                self.collection = self.chroma_client.get_or_create_collection(
                    name="financial_documents",
                    metadata={"description": "Financial documents for RAG"}
                )
                logger.info("Initialized ChromaDB collection")
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB: {e}")

    def is_available(self) -> bool:
        """Check if RAG service is fully available"""
        return HAS_PDF_SUPPORT and HAS_EMBEDDINGS and HAS_CHROMADB

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extract text from PDF file

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text
        """
        if not HAS_PDF_SUPPORT:
            return ""

        try:
            text = ""
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"

            logger.info(f"Extracted {len(text)} characters from {pdf_path}")
            return text

        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return ""

    def chunk_text(self, text: str, chunk_size: int = 400,
                   overlap: int = 50) -> List[Dict[str, Any]]:
        """
        Chunk text into smaller pieces with overlap

        Args:
            text: Input text
            chunk_size: Target chunk size in tokens (approx)
            overlap: Overlap between chunks

        Returns:
            List of chunk dictionaries
        """
        # Simple word-based chunking (approximate tokens)
        words = text.split()
        chunks = []

        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)

            chunks.append({
                'text': chunk_text,
                'start_idx': i,
                'end_idx': min(i + chunk_size, len(words)),
                'word_count': len(chunk_words)
            })

        logger.info(f"Created {len(chunks)} chunks from text")
        return chunks

    def ingest_document(self, pdf_path: str, document_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Ingest a PDF document into the RAG system

        Args:
            pdf_path: Path to PDF file
            document_metadata: Optional metadata (company, report_type, date, etc.)

        Returns:
            Ingestion result
        """
        if not self.is_available():
            return {
                'error': 'RAG service not fully available',
                'missing_dependencies': {
                    'pdf': not HAS_PDF_SUPPORT,
                    'embeddings': not HAS_EMBEDDINGS,
                    'chromadb': not HAS_CHROMADB
                }
            }

        try:
            # Extract text
            text = self.extract_text_from_pdf(pdf_path)
            if not text:
                return {'error': 'Failed to extract text from PDF'}

            # Chunk text
            chunks = self.chunk_text(text)

            # Generate document ID
            doc_id = hashlib.md5(text.encode()).hexdigest()[:16]

            # Prepare metadata
            metadata = document_metadata or {}
            metadata['filename'] = os.path.basename(pdf_path)
            metadata['ingestion_date'] = datetime.now().isoformat()
            metadata['doc_id'] = doc_id
            metadata['num_chunks'] = len(chunks)

            # Generate embeddings for each chunk
            chunk_texts = [chunk['text'] for chunk in chunks]
            embeddings = self.embeddings_model.encode(chunk_texts).tolist()

            # Store in ChromaDB
            ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    **metadata,
                    'chunk_idx': i,
                    'start_idx': chunk['start_idx'],
                    'end_idx': chunk['end_idx']
                }
                for i, chunk in enumerate(chunks)
            ]

            self.collection.add(
                embeddings=embeddings,
                documents=chunk_texts,
                metadatas=metadatas,
                ids=ids
            )

            logger.info(f"Ingested document {doc_id} with {len(chunks)} chunks")

            return {
                'success': True,
                'doc_id': doc_id,
                'num_chunks': len(chunks),
                'metadata': metadata
            }

        except Exception as e:
            logger.error(f"Error ingesting document: {e}")
            return {'error': str(e)}

    def search(self, query: str, top_k: int = 5,
              filter_metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Search for relevant document chunks

        Args:
            query: Search query
            top_k: Number of top results to return
            filter_metadata: Optional metadata filters

        Returns:
            List of relevant chunks with metadata
        """
        if not self.is_available():
            return []

        try:
            # Generate query embedding
            query_embedding = self.embeddings_model.encode([query])[0].tolist()

            # Search in ChromaDB
            where_filter = filter_metadata if filter_metadata else None

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter
            )

            # Format results
            formatted_results = []
            if results and 'documents' in results and results['documents']:
                for i in range(len(results['documents'][0])):
                    formatted_results.append({
                        'text': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i] if 'metadatas' in results else {},
                        'distance': results['distances'][0][i] if 'distances' in results else None
                    })

            logger.info(f"Found {len(formatted_results)} results for query: {query[:50]}...")
            return formatted_results

        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []

    def build_context(self, query: str, top_k: int = 3,
                     filter_metadata: Dict[str, Any] = None) -> str:
        """
        Build context string for LLM from search results

        Args:
            query: User query
            top_k: Number of chunks to retrieve
            filter_metadata: Optional metadata filters

        Returns:
            Context string formatted for LLM
        """
        results = self.search(query, top_k, filter_metadata)

        if not results:
            return "No relevant information found in documents."

        context_parts = []
        for i, result in enumerate(results, 1):
            metadata = result.get('metadata', {})
            doc_info = f"Document: {metadata.get('filename', 'Unknown')}"
            if 'report_type' in metadata:
                doc_info += f" ({metadata['report_type']})"

            context_parts.append(f"[Source {i}] {doc_info}\n{result['text']}")

        context = "\n\n".join(context_parts)
        return context

    def get_document_summary(self, doc_id: str = None) -> Dict[str, Any]:
        """
        Get summary of ingested documents

        Args:
            doc_id: Optional document ID to filter

        Returns:
            Document summary
        """
        if not self.is_available():
            return {'error': 'RAG service not available'}

        try:
            # Get collection count
            count = self.collection.count()

            result = {
                'total_chunks': count,
                'collection_name': self.collection.name,
                'status': 'active' if count > 0 else 'empty'
            }

            if doc_id:
                # Get specific document chunks
                doc_results = self.collection.get(
                    where={"doc_id": doc_id}
                )
                result['doc_id'] = doc_id
                result['doc_chunks'] = len(doc_results['ids']) if doc_results else 0

            return result

        except Exception as e:
            logger.error(f"Error getting document summary: {e}")
            return {'error': str(e)}

    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """
        Delete a document from the collection

        Args:
            doc_id: Document ID to delete

        Returns:
            Deletion result
        """
        if not self.is_available():
            return {'error': 'RAG service not available'}

        try:
            # Get all chunk IDs for this document
            doc_results = self.collection.get(
                where={"doc_id": doc_id}
            )

            if not doc_results or not doc_results['ids']:
                return {'error': f'Document {doc_id} not found'}

            # Delete all chunks
            self.collection.delete(ids=doc_results['ids'])

            logger.info(f"Deleted document {doc_id} ({len(doc_results['ids'])} chunks)")

            return {
                'success': True,
                'doc_id': doc_id,
                'deleted_chunks': len(doc_results['ids'])
            }

        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return {'error': str(e)}


# Singleton instance
rag_service = RAGService()


# Helper functions
def ingest_pdf(pdf_path: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """Ingest a PDF document"""
    return rag_service.ingest_document(pdf_path, metadata)


def search_documents(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Search documents"""
    return rag_service.search(query, top_k)


def get_context_for_query(query: str, top_k: int = 3) -> str:
    """Get context string for LLM"""
    return rag_service.build_context(query, top_k)