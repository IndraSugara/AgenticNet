"""
LangChain RAG Tools for Network Knowledge Base

Tools for searching and managing the network knowledge base:
- Search for troubleshooting guides
- Add new knowledge
- Get context for queries
"""
from langchain_core.tools import tool
from typing import List, Optional


@tool
def search_knowledge(query: str, category: str = None) -> str:
    """
    Search the network knowledge base for relevant information.
    
    Use this tool when the user asks about:
    - Network troubleshooting steps
    - Configuration guides
    - Best practices
    - Port information
    - How to fix network issues
    
    Args:
        query: Search query describing what you need
        category: Optional filter - troubleshooting, documentation, guide
    
    Returns:
        Relevant knowledge from the database
    """
    from agent.rag_knowledge import get_knowledge_base
    
    kb = get_knowledge_base()
    
    try:
        docs = kb.search(query, k=3, category=category)
        
        if not docs:
            return "Tidak ditemukan informasi yang relevan di knowledge base."
        
        result_parts = [f"📚 Ditemukan {len(docs)} dokumen relevan:\n"]
        
        for i, doc in enumerate(docs, 1):
            title = doc.metadata.get("title", "Untitled")
            category = doc.metadata.get("category", "general")
            result_parts.append(f"### {i}. {title} [{category}]")
            result_parts.append(doc.page_content[:1000])  # Limit content length
            result_parts.append("")
        
        return "\n".join(result_parts)
    
    except Exception as e:
        return f"Error searching knowledge base: {str(e)}"


@tool
def add_knowledge(title: str, content: str, category: str, tags: str = "") -> str:
    """
    Add new knowledge to the database.
    
    Use this to save important information for future reference.
    
    Args:
        title: Title of the knowledge entry
        content: The actual content/information to save
        category: Category - troubleshooting, documentation, guide, config
        tags: Comma-separated tags for searchability
    
    Returns:
        Confirmation message
    """
    from agent.rag_knowledge import get_knowledge_base
    
    kb = get_knowledge_base()
    
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        
        doc_id = kb.add_document(
            title=title,
            content=content,
            category=category,
            tags=tag_list
        )
        
        return f"✅ Knowledge berhasil ditambahkan!\n\nTitle: {title}\nCategory: {category}\nTags: {', '.join(tag_list) if tag_list else 'None'}\nID: {doc_id}"
    
    except Exception as e:
        return f"❌ Gagal menambahkan knowledge: {str(e)}"


@tool
def get_knowledge_stats() -> str:
    """
    Get statistics about the knowledge base.
    
    Returns:
        Summary of knowledge base contents
    """
    from agent.rag_knowledge import get_knowledge_base
    
    kb = get_knowledge_base()
    
    try:
        count = kb.count_documents()
        categories = kb.list_categories()
        
        lines = [
            "📊 Knowledge Base Statistics",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Total Documents: {count}",
            f"Categories: {', '.join(categories) if categories else 'None'}",
        ]
        
        return "\n".join(lines)
    
    except Exception as e:
        return f"Error getting stats: {str(e)}"


@tool
def initialize_knowledge_base() -> str:
    """
    Initialize the knowledge base with default network knowledge.
    
    Run this once to populate the knowledge base with:
    - Troubleshooting guides
    - Configuration documentation
    - Best practices
    - Port references
    
    Returns:
        Confirmation with number of documents added
    """
    from agent.rag_knowledge import get_knowledge_base
    
    kb = get_knowledge_base()
    
    try:
        count = kb.initialize_with_defaults()
        return f"✅ Knowledge base initialized with {count} default documents!\n\nYou can now use search_knowledge to query the knowledge base."
    
    except Exception as e:
        return f"❌ Error initializing: {str(e)}"


# Export all RAG tools
def get_rag_tools() -> list:
    """Get all RAG/knowledge base tools"""
    return [
        search_knowledge,
        add_knowledge,
        get_knowledge_stats,
        initialize_knowledge_base,
    ]
