import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import UUID

from fastapi import HTTPException


def resolve_minecraft_username(username: str) -> tuple[str, str]:
    request = Request(
        f"https://api.mojang.com/users/profiles/minecraft/{quote(username, safe='')}",
        headers={"Accept": "application/json", "User-Agent": "GrindPvP/1.0"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            if response.status == 204:
                raise HTTPException(status_code=404, detail="Minecraft username was not found.")
            profile = json.loads(response.read())
    except HTTPError as error:
        if error.code == 404:
            raise HTTPException(status_code=404, detail="Minecraft username was not found.") from error
        if error.code == 429:
            raise HTTPException(status_code=503, detail="Minecraft profile service is rate limited. Try again shortly.") from error
        raise HTTPException(status_code=502, detail="Minecraft profile service returned an error.") from error
    except (TimeoutError, URLError, OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail="Could not reach the Minecraft profile service.") from error

    try:
        player_uuid = str(UUID(profile["id"]))
        resolved_username = profile["name"]
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Minecraft profile service returned an invalid profile.") from error
    if resolved_username.lower() != username.lower():
        raise HTTPException(status_code=409, detail="Minecraft profile lookup returned a different username.")
    return player_uuid, resolved_username
