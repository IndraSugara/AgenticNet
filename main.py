"""
Agentic AI Network Infrastructure Operator

Main entry point for the application.
"""
import uvicorn
from config import config


def main():
    """Run the application"""
    
    uvicorn.run(
        "web.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )


if __name__ == "__main__":
    main()
