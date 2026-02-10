"""
RAG (Retrieval-Augmented Generation) Module for Network Knowledge Base

Uses ChromaDB for vector storage and retrieval of:
- Network troubleshooting guides
- Device documentation
- Best practices
- Configuration templates
"""
import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_community.embeddings import OllamaEmbeddings

from config import config


# Data directory for ChromaDB
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma_db")


@dataclass
class KnowledgeEntry:
    """A knowledge base entry"""
    title: str
    content: str
    category: str
    tags: List[str]
    source: str = "manual"
    
    def to_document(self) -> Document:
        """Convert to LangChain Document"""
        return Document(
            page_content=f"# {self.title}\n\n{self.content}",
            metadata={
                "title": self.title,
                "category": self.category,
                "tags": ",".join(self.tags),
                "source": self.source
            }
        )


class NetworkKnowledgeBase:
    """
    Vector-based knowledge base for network operations
    
    Features:
    - Store and retrieve network documentation
    - Semantic search for troubleshooting
    - Category-based organization
    """
    
    def __init__(self, persist_directory: str = None):
        """
        Initialize the knowledge base
        
        Args:
            persist_directory: Directory to persist ChromaDB data
        """
        self.persist_directory = persist_directory or CHROMA_DIR
        os.makedirs(self.persist_directory, exist_ok=True)
        
        # Initialize embeddings
        self._embeddings = None
        self._vectorstore = None
        self._initialized = False
    
    def _get_embeddings(self) -> Embeddings:
        """Get or create embeddings model"""
        if self._embeddings is None:
            self._embeddings = OllamaEmbeddings(
                model=config.OLLAMA_MODEL,
                base_url=config.OLLAMA_HOST
            )
        return self._embeddings
    
    def _get_vectorstore(self) -> Chroma:
        """Get or create ChromaDB vectorstore"""
        if self._vectorstore is None:
            self._vectorstore = Chroma(
                collection_name="network_knowledge",
                embedding_function=self._get_embeddings(),
                persist_directory=self.persist_directory
            )
            self._initialized = True
        return self._vectorstore
    
    def add_document(self, title: str, content: str, category: str, tags: List[str] = None) -> str:
        """
        Add a document to the knowledge base
        
        Args:
            title: Document title
            content: Document content
            category: Category (troubleshooting, documentation, guide, config)
            tags: Optional list of tags
            
        Returns:
            Document ID
        """
        entry = KnowledgeEntry(
            title=title,
            content=content,
            category=category,
            tags=tags or []
        )
        
        doc = entry.to_document()
        vectorstore = self._get_vectorstore()
        ids = vectorstore.add_documents([doc])
        
        return ids[0] if ids else None
    
    def add_documents(self, documents: List[Dict[str, Any]]) -> List[str]:
        """
        Add multiple documents at once
        
        Args:
            documents: List of dicts with title, content, category, tags
            
        Returns:
            List of document IDs
        """
        docs = []
        for d in documents:
            entry = KnowledgeEntry(
                title=d.get("title", "Untitled"),
                content=d.get("content", ""),
                category=d.get("category", "general"),
                tags=d.get("tags", [])
            )
            docs.append(entry.to_document())
        
        vectorstore = self._get_vectorstore()
        return vectorstore.add_documents(docs)
    
    def search(self, query: str, k: int = 3, category: str = None) -> List[Document]:
        """
        Search for relevant documents
        
        Args:
            query: Search query
            k: Number of results to return
            category: Optional category filter
            
        Returns:
            List of relevant documents
        """
        vectorstore = self._get_vectorstore()
        
        if category:
            results = vectorstore.similarity_search(
                query,
                k=k,
                filter={"category": category}
            )
        else:
            results = vectorstore.similarity_search(query, k=k)
        
        return results
    
    def search_with_scores(self, query: str, k: int = 3) -> List[tuple]:
        """
        Search with relevance scores
        
        Args:
            query: Search query
            k: Number of results
            
        Returns:
            List of (document, score) tuples
        """
        vectorstore = self._get_vectorstore()
        return vectorstore.similarity_search_with_score(query, k=k)
    
    def get_context_for_query(self, query: str, k: int = 3) -> str:
        """
        Get formatted context string for RAG
        
        Args:
            query: User query
            k: Number of documents to retrieve
            
        Returns:
            Formatted context string
        """
        docs = self.search(query, k=k)
        
        if not docs:
            return ""
        
        context_parts = ["## Relevant Knowledge:\n"]
        for i, doc in enumerate(docs, 1):
            title = doc.metadata.get("title", "Unknown")
            context_parts.append(f"### {i}. {title}\n{doc.page_content}\n")
        
        return "\n".join(context_parts)
    
    def list_categories(self) -> List[str]:
        """Get all unique categories"""
        vectorstore = self._get_vectorstore()
        collection = vectorstore._collection
        
        # Get all metadata
        results = collection.get(include=["metadatas"])
        categories = set()
        
        for meta in results.get("metadatas", []):
            if meta and "category" in meta:
                categories.add(meta["category"])
        
        return list(categories)
    
    def count_documents(self) -> int:
        """Get total number of documents"""
        vectorstore = self._get_vectorstore()
        return vectorstore._collection.count()
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document by ID"""
        vectorstore = self._get_vectorstore()
        try:
            vectorstore.delete([doc_id])
            return True
        except Exception:
            return False
    
    def initialize_with_defaults(self):
        """Initialize with default network knowledge"""
        default_docs = get_default_knowledge()
        self.add_documents(default_docs)
        return len(default_docs)


def get_default_knowledge() -> List[Dict[str, Any]]:
    """Get default network troubleshooting knowledge"""
    return [
        {
            "title": "Troubleshooting Koneksi Internet",
            "content": """
Langkah-langkah troubleshooting koneksi internet:

1. **Cek koneksi fisik**
   - Pastikan kabel LAN terpasang dengan benar
   - Cek lampu indikator di router/modem
   
2. **Cek IP Address**
   - Jalankan `ipconfig` (Windows) atau `ip addr` (Linux)
   - Pastikan mendapat IP dari DHCP
   
3. **Ping Gateway**
   - Ping IP gateway (biasanya 192.168.1.1)
   - Jika gagal, masalah di jaringan lokal
   
4. **Ping DNS Publik**
   - Ping 8.8.8.8 (Google DNS)
   - Jika berhasil tapi tidak bisa browsing, masalah DNS
   
5. **Cek DNS**
   - Gunakan nslookup untuk test DNS
   - Coba ganti DNS ke 8.8.8.8 atau 1.1.1.1
""",
            "category": "troubleshooting",
            "tags": ["internet", "koneksi", "dns", "gateway"]
        },
        {
            "title": "Konfigurasi Router Mikrotik Basic",
            "content": """
Konfigurasi dasar router Mikrotik:

## Akses Router
- Default IP: 192.168.88.1
- Default user: admin (no password)
- Akses via Winbox, WebFig, atau SSH

## Setup Internet
```
/ip address add address=192.168.1.2/24 interface=ether1
/ip route add gateway=192.168.1.1
/ip dns set servers=8.8.8.8,8.8.4.4
```

## Setup DHCP Server
```
/ip pool add name=dhcp_pool ranges=192.168.88.10-192.168.88.254
/ip dhcp-server network add address=192.168.88.0/24 gateway=192.168.88.1
/ip dhcp-server add name=dhcp1 interface=bridge disabled=no
```

## Setup NAT
```
/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade
```
""",
            "category": "documentation",
            "tags": ["mikrotik", "router", "konfigurasi", "dhcp"]
        },
        {
            "title": "Port Network Umum",
            "content": """
Daftar port network yang umum digunakan:

## Web Services
- 80: HTTP
- 443: HTTPS
- 8080: HTTP Alternate

## Remote Access
- 22: SSH
- 23: Telnet
- 3389: RDP (Remote Desktop)

## File Transfer
- 21: FTP
- 22: SFTP/SCP
- 445: SMB/CIFS

## Email
- 25: SMTP
- 110: POP3
- 143: IMAP
- 587: SMTP Submission

## Database
- 3306: MySQL
- 5432: PostgreSQL
- 1433: MS SQL Server
- 27017: MongoDB

## Network Services
- 53: DNS
- 67/68: DHCP
- 161/162: SNMP
- 123: NTP
""",
            "category": "documentation",
            "tags": ["port", "network", "referensi"]
        },
        {
            "title": "Troubleshooting Latency Tinggi",
            "content": """
Cara mengatasi latency/ping tinggi:

## Identifikasi Masalah
1. Gunakan `ping -t` untuk monitor terus-menerus
2. Gunakan `traceroute` untuk identifikasi hop yang lambat
3. Cek penggunaan bandwidth dengan `get_bandwidth_stats`

## Penyebab Umum
1. **Bandwidth penuh** - Terlalu banyak pengguna
2. **Interferensi WiFi** - Channel terlalu padat
3. **Routing buruk** - ISP bermasalah
4. **Hardware bermasalah** - Router/switch overheat

## Solusi
1. **QoS** - Prioritaskan traffic penting
2. **Ganti channel WiFi** - Gunakan channel yang kosong
3. **Upgrade bandwidth** - Jika sering full
4. **Restart perangkat** - Router, modem, switch
5. **Cek kabel** - Kabel rusak bisa sebabkan packet loss
""",
            "category": "troubleshooting",
            "tags": ["latency", "ping", "lambat", "bandwidth"]
        },
        {
            "title": "Best Practice Keamanan Jaringan",
            "content": """
Best practice keamanan jaringan kantor:

## Password & Akses
- Gunakan password kompleks minimal 12 karakter
- Ganti password default semua perangkat
- Implementasi 2FA jika memungkinkan
- Batasi akses admin berdasarkan IP

## Firewall
- Default deny, explicit allow
- Block traffic masuk yang tidak perlu
- Logging semua rejected traffic
- Regular review firewall rules

## Update & Patch
- Update firmware perangkat secara berkala
- Patch sistem operasi server
- Subscribe security advisory vendor

## Monitoring
- Aktifkan logging di semua perangkat
- Monitor traffic anomali
- Setup alerting untuk kejadian penting
- Regular security audit

## Segmentasi
- Pisahkan VLAN untuk guest
- Isolasi server dari client network
- DMZ untuk public-facing services
""",
            "category": "guide",
            "tags": ["security", "keamanan", "best-practice", "firewall"]
        }
    ]


# Singleton instance
_knowledge_base = None


def get_knowledge_base() -> NetworkKnowledgeBase:
    """Get or create knowledge base singleton"""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = NetworkKnowledgeBase()
    return _knowledge_base
