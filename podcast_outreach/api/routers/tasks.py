from fastapi import APIRouter

router = APIRouter()
 
@router.get("/tasks/")
async def get_tasks():
    return {"message": "Tasks endpoint"} 

# Placeholder for tasks API routes 