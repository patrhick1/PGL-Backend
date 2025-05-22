from fastapi import APIRouter

router = APIRouter()
 
@router.get("/media/")
async def get_media():
    return {"message": "Media endpoint"} 

# Placeholder for media API routes 