from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
import uvicorn
import logging
import asyncio
import os
from contextlib import asynccontextmanager
from config import MONGO_URL, DATABASE_URL
from utils import LOGGER

app = FastAPI(title="Smart Bot Stats API", description="API for retrieving bot usage statistics")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LOGGER.info("Creating MONGO_CLIENT From MONGO_URL")
try:
    parsed = urlparse(MONGO_URL)
    query_params = parse_qs(parsed.query)
    db_name = query_params.get("appName", [None])[0]
    if not db_name:
        raise ValueError("No database name found in MONGO_URL (missing 'appName' query param)")
    MONGO_CLIENT = AsyncIOMotorClient(MONGO_URL)
    db_mongo = MONGO_CLIENT.get_database(db_name)
    user_activity_collection = db_mongo["user_activity"]
    LOGGER.info("MONGO_CLIENT Created Successfully!")
except Exception as e:
    LOGGER.error(f"Failed to create MONGO_CLIENT: {e}")
    raise

LOGGER.info("Creating Database Client From DATABASE_URL")
try:
    parsed = urlparse(DATABASE_URL)
    query_params = parse_qs(parsed.query)
    db_name = query_params.get("appName", [None])[0]
    if not db_name:
        raise ValueError("No database name found in DATABASE_URL (missing 'appName' query param)")
    mongo_client = AsyncIOMotorClient(DATABASE_URL)
    db = mongo_client.get_database(db_name)
    auth_admins = db["auth_admins"]
    banned_users = db["banned_users"]
    LOGGER.info("Database Client Created Successfully!")
except Exception as e:
    LOGGER.error(f"Database Client Create Error: {e}")
    raise

@asynccontextmanager
async def lifespan(app):
    try:
        await MONGO_CLIENT.admin.command("ping")
        await mongo_client.admin.command("ping")
        LOGGER.info("Successfully connected to MongoDB for both clients")
    except Exception as e:
        LOGGER.error(f"Failed to connect to MongoDB: {str(e)}")
        raise HTTPException(status_code=500, detail="Database connection failed")
    yield
    MONGO_CLIENT.close()
    mongo_client.close()
    LOGGER.info("MongoDB connections closed")

app.lifespan = lifespan

@app.get("/", response_class=HTMLResponse)
async def get_index():
    try:
        with open("index.html", "r") as file:
            html_content = file.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        LOGGER.error("index.html file not found")
        raise HTTPException(status_code=404, detail="Index file not found")
    except Exception as e:
        LOGGER.error(f"Error serving index.html: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to serve index page")

@app.get("/api/stats")
async def get_stats():
    try:
        now = datetime.utcnow()
        daily_users = await user_activity_collection.count_documents({
            "is_group": False,
            "last_activity": {"$gte": now - timedelta(days=1)}
        })
        weekly_users = await user_activity_collection.count_documents({
            "is_group": False,
            "last_activity": {"$gte": now - timedelta(weeks=1)}
        })
        monthly_users = await user_activity_collection.count_documents({
            "is_group": False,
            "last_activity": {"$gte": now - timedelta(days=30)}
        })
        yearly_users = await user_activity_collection.count_documents({
            "is_group": False,
            "last_activity": {"$gte": now - timedelta(days=365)}
        })
        total_users = await user_activity_collection.count_documents({"is_group": False})
        total_groups = await user_activity_collection.count_documents({"is_group": True})

        response = {
            "api_owner": "@ISmartCoder",
            "api_dev": "@TheSmartDev",
            "stats": {
                "daily_users": daily_users,
                "weekly_users": weekly_users,
                "monthly_users": monthly_users,
                "yearly_users": yearly_users,
                "total_users": total_users,
                "total_groups": total_groups
            },
            "timestamp": now.isoformat()
        }
        
        LOGGER.info("Successfully retrieved stats")
        return response
    except Exception as e:
        LOGGER.error(f"Error retrieving stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve stats")

@app.get("/api/banlist")
async def get_banlist():
    try:
        banned_list = await banned_users.find({}).to_list(None)
        if not banned_list:
            return {
                "api_owner": "@ISmartCoder",
                "api_dev": "@TheSmartDev",
                "banned_users": [],
                "total_banned": 0,
                "timestamp": datetime.utcnow().isoformat()
            }
        
        response = {
            "api_owner": "@ISmartCoder",
            "api_dev": "@TheSmartDev",
            "banned_users": [
                {
                    "user_id": user["user_id"],
                    "full_name": user.get("username", str(user["user_id"])),
                    "reason": user.get("reason", "Undefined"),
                    "ban_date": user.get("ban_date", "Undefined")
                } for user in banned_list
            ],
            "total_banned": len(banned_list),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        LOGGER.info("Successfully retrieved banlist")
        return response
    except Exception as e:
        LOGGER.error(f"Error retrieving banlist: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve banlist")

@app.get("/api/adminlist")
async def get_adminlist():
    try:
        admins = await auth_admins.find({}, {
            "user_id": 1, "title": 1, "auth_date": 1, "username": 1,
            "full_name": 1, "auth_time": 1, "auth_by": 1, "_id": 0
        }).to_list(None)
        
        admin_list = [
            {
                "user_id": 7666341631,
                "full_name": "Abir Arafat Chawdhury 🇧🇩",
                "title": "Owner",
                "username": "@ISmartCoder",
                "auth_date": "Infinity",
                "auth_time": "Infinity",
                "auth_by": "Abir Arafat Chawdhury"
            }
        ]
        
        admin_list.extend([
            {
                "user_id": admin["user_id"],
                "full_name": admin.get("full_name", "Unknown"),
                "title": admin["title"],
                "username": admin.get("username", "None"),
                "auth_date": admin.get("auth_date", admin.get("auth_time", datetime.utcnow())).strftime("%Y-%m-%d") if isinstance(admin.get("auth_date"), datetime) else "Unknown",
                "auth_time": admin.get("auth_time", datetime.utcnow()).strftime("%H:%M:%S"),
                "auth_by": admin.get("auth_by", "Unknown")
            } for admin in admins
        ])
        
        response = {
            "api_owner": "@ISmartCoder",
            "api_dev": "@TheSmartDev",
            "admins": admin_list,
            "total_admins": len(admin_list),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        LOGGER.info("Successfully retrieved adminlist")
        return response
    except Exception as e:
        LOGGER.error(f"Error retrieving adminlist: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve adminlist")

async def main():
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        workers=4,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
