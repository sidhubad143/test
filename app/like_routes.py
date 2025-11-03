from flask import Blueprint, request, jsonify
import asyncio
from datetime import datetime, timezone
import logging
import aiohttp 

from .utils.protobuf_utils import encode_uid, create_protobuf 
from .utils.crypto_utils import encrypt_aes
from .token_manager import get_headers 

logger = logging.getLogger(__name__)

like_bp = Blueprint('like_bp', __name__)

_SERVERS = {}
_token_cache = None

async def async_post_request(url: str, data: bytes, token: str):
    try:
        headers = get_headers(token)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers, timeout=10) as resp:
                return await resp.read()
    except Exception as e:
        logger.error(f"Async request failed: {str(e)}")
        return None

async def send_likes(uid: str, region: str = "BR"):
    tokens = _token_cache.get_tokens(region)
    if not tokens:
        logger.warning(f"No tokens for {region}, cannot send likes.")
        return {'sent': 0, 'added': 0}
    
    like_url = f"{_SERVERS[region]}/LikeProfile"
    encrypted = encrypt_aes(create_protobuf(uid, region))

    tasks = [async_post_request(like_url, bytes.fromhex(encrypted), token) for token in tokens]
    results = await asyncio.gather(*tasks)

    added = sum(1 for r in results if r is not None)
    logger.info(f"Sent {len(results)} likes to UID {uid} on {region}, successful: {added}")

    return {
        'sent': len(results),
        'added': added
    }

@like_bp.route("/like", methods=["GET"])
async def like_player():
    try:
        uid = request.args.get("uid")
        if not uid or not uid.isdigit():
            return jsonify({
                "error": "Invalid UID",
                "message": "Valid numeric UID required",
                "status": 400,
                "credits": "https://t.me/nopethug"
            }), 400

        # FIXED: Skip detection, hardcoded BR region, no profile fetch
        region = "BR"  # Use BR as default (has tokens)
        tokens = _token_cache.get_tokens(region)
        if not tokens:
            return jsonify({
                "error": "No valid tokens",
                "message": "No tokens available for BR. Check /health-check.",
                "status": 404,
                "credits": "https://t.me/nopethug"
            }), 404

        # Assume before_likes = 0 (no fetch), likes_added = successful sends
        likes_added = (await send_likes(uid, region))['added']
        likes_before = 0  # Simplified, no fetch
        likes_after = likes_added

        return jsonify({
            "player": "Unknown",  # No profile fetch
            "uid": uid,
            "likes_added": likes_added,
            "likes_before": likes_before,
            "likes_after": likes_after,
            "server_used": region,
            "status": 1 if likes_added > 0 else 2,
            "credits": "https://t.me/nopethug"
        })

    except Exception as e:
        logger.error(f"Like error for UID {uid}: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Internal server error",
            "message": str(e),
            "status": 500,
            "credits": "https://t.me/nopethug"
        }), 500

@like_bp.route("/health-check", methods=["GET"])
def health_check():
    try:
        token_status = {
            server: len(_token_cache.get_tokens(server)) > 0 
            for server in _SERVERS 
        }

        return jsonify({
            "status": "healthy" if all(token_status.values()) else "degraded",
            "servers": token_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "credits": "https://t.me/nopethug"
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "credits": "https://t.me/nopethug"
        }), 500

@like_bp.route("/", methods=["GET"]) 
async def root_home():
    return jsonify({
        "message": "Api free fire like (Simplified: Direct BR likes, no profile)",
        "credits": "https://t.me/nopethug",
    })

def initialize_routes(app_instance, servers_config, token_cache_instance):
    global _SERVERS, _token_cache 
    _SERVERS = servers_config
    _token_cache = token_cache_instance
    app_instance.register_blueprint(like_bp)
