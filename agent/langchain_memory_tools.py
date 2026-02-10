"""
LangChain Memory Tools

Tools for interacting with the agent's long-term memory.
"""
from typing import Optional
from langchain_core.tools import tool

from agent.long_term_memory import long_term_memory


@tool
def remember_solution(
    problem: str,
    solution: str,
    category: str = "network"
) -> str:
    """
    Save a troubleshooting solution to memory for future reference.
    
    Args:
        problem: Description of the problem that was solved
        solution: The solution that worked
        category: Category (network, device, config, security, etc.)
    
    Returns:
        Confirmation of saved solution
    """
    try:
        saved = long_term_memory.save_solution(
            problem=problem,
            solution=solution,
            category=category
        )
        
        return f"""✅ Solution saved to memory!

**Problem:** {problem[:100]}{"..." if len(problem) > 100 else ""}
**Category:** {category}
**Times Used:** {saved.success_count}

This solution will be suggested for similar problems in the future."""
    except Exception as e:
        return f"❌ Failed to save solution: {str(e)}"


@tool
def recall_similar_solutions(
    problem: str,
    category: str = None
) -> str:
    """
    Find similar solutions from past troubleshooting experiences.
    
    Args:
        problem: Description of the current problem
        category: Optional category filter
    
    Returns:
        List of similar past solutions
    """
    try:
        # Extract keywords for search
        keywords = " OR ".join(problem.split()[:5])
        
        solutions = long_term_memory.find_similar_solutions(
            query=keywords,
            category=category,
            limit=5
        )
        
        if not solutions:
            # Try top solutions as fallback
            solutions = long_term_memory.get_top_solutions(
                category=category,
                limit=3
            )
            
            if not solutions:
                return "ℹ️ No similar solutions found in memory. This might be a new type of problem."
            
            output = "## Top Solutions (General)\n\n"
        else:
            output = "## Similar Solutions Found\n\n"
        
        for i, sol in enumerate(solutions, 1):
            output += f"### {i}. {sol.category.title()} Solution\n"
            output += f"**Problem:** {sol.problem[:150]}{'...' if len(sol.problem) > 150 else ''}\n"
            output += f"**Solution:** {sol.solution[:300]}{'...' if len(sol.solution) > 300 else ''}\n"
            output += f"_Used {sol.success_count} times | Last used: {sol.last_used[:10]}_\n\n"
        
        return output
    except Exception as e:
        return f"❌ Error searching memory: {str(e)}"


@tool
def get_user_preference(key: str) -> str:
    """
    Get a saved user preference.
    
    Args:
        key: Preference key (e.g., "default_dns", "ping_count", "language")
    
    Returns:
        Preference value or default message
    """
    try:
        value = long_term_memory.get_preference(key)
        
        if value:
            return f"**{key}:** {value}"
        else:
            return f"ℹ️ No preference set for '{key}'."
    except Exception as e:
        return f"❌ Error getting preference: {str(e)}"


@tool
def set_user_preference(key: str, value: str) -> str:
    """
    Save a user preference for future sessions.
    
    Args:
        key: Preference key (e.g., "default_dns", "ping_count", "language")
        value: Preference value
    
    Returns:
        Confirmation
    """
    try:
        long_term_memory.set_preference(key, value)
        return f"✅ Preference saved: **{key}** = {value}"
    except Exception as e:
        return f"❌ Error saving preference: {str(e)}"


@tool
def get_all_preferences() -> str:
    """
    Get all saved user preferences.
    
    Returns:
        List of all preferences
    """
    try:
        prefs = long_term_memory.get_all_preferences()
        
        if not prefs:
            return "ℹ️ No preferences saved yet."
        
        output = "## User Preferences\n\n"
        for key, value in prefs.items():
            output += f"- **{key}:** {value}\n"
        
        return output
    except Exception as e:
        return f"❌ Error getting preferences: {str(e)}"


@tool
def get_top_solutions(category: str = None) -> str:
    """
    Get the most successful solutions from memory.
    
    Args:
        category: Optional category filter
    
    Returns:
        List of top solutions
    """
    try:
        solutions = long_term_memory.get_top_solutions(category=category, limit=10)
        
        if not solutions:
            return "ℹ️ No solutions stored in memory yet."
        
        cat_text = f" ({category})" if category else ""
        output = f"## Top Solutions{cat_text}\n\n"
        
        for i, sol in enumerate(solutions, 1):
            output += f"**{i}. [{sol.category}]** {sol.problem[:80]}...\n"
            output += f"   _Used {sol.success_count} times_\n\n"
        
        return output
    except Exception as e:
        return f"❌ Error getting solutions: {str(e)}"


@tool
def get_memory_stats() -> str:
    """
    Get statistics about the agent's memory.
    
    Returns:
        Memory statistics
    """
    try:
        stats = long_term_memory.get_memory_stats()
        
        return f"""## Agent Memory Statistics

**Solutions Stored:** {stats['solutions_stored']}
**Total Solution Uses:** {stats['total_solution_uses']}
**Preferences Saved:** {stats['preferences_count']}
**Patterns Learned:** {stats['patterns_learned']}

_The agent learns from successful troubleshooting to provide better solutions over time._
"""
    except Exception as e:
        return f"❌ Error getting stats: {str(e)}"


@tool
def learn_pattern(pattern_type: str, description: str) -> str:
    """
    Record a learned pattern for the agent.
    
    Args:
        pattern_type: Type of pattern (command, issue, behavior)
        description: Description of the pattern
    
    Returns:
        Confirmation
    """
    try:
        long_term_memory.record_pattern(
            pattern_type=pattern_type,
            pattern_data={"description": description}
        )
        
        return f"✅ Pattern recorded: [{pattern_type}] {description[:50]}..."
    except Exception as e:
        return f"❌ Error recording pattern: {str(e)}"


def get_memory_tools() -> list:
    """Get all memory-related tools"""
    return [
        remember_solution,
        recall_similar_solutions,
        get_user_preference,
        set_user_preference,
        get_all_preferences,
        get_top_solutions,
        get_memory_stats,
        learn_pattern,
    ]
