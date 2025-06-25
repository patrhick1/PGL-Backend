# CORS configuration helper
import os

def get_allowed_origins():
    """
    Get allowed origins for CORS from environment.
    Supports comma-separated values for multiple origins.
    """
    origins = ["http://localhost:5173"]  # Always include for local dev
    
    # Get from environment
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip()
    
    if frontend_origin:
        # Support comma-separated origins
        if "," in frontend_origin:
            for origin in frontend_origin.split(","):
                origin = origin.strip()
                if origin and origin not in origins:
                    origins.append(origin)
        else:
            if frontend_origin not in origins:
                origins.append(frontend_origin)
    
    # Always include the known frontend URLs
    known_frontends = [
        "https://podcastguestlaunch.replit.app",
        "https://podcastguestlaunch.replit.app/"  # With trailing slash
    ]
    for frontend in known_frontends:
        if frontend not in origins:
            origins.append(frontend)
    
    # In production, you might want to remove localhost
    if os.getenv("IS_PRODUCTION", "false").lower() == "true":
        # Remove localhost in production unless explicitly included
        if "http://localhost:5173" in origins and len(origins) > 1:
            origins.remove("http://localhost:5173")
    
    return origins