import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

LOGGER = logging.getLogger(__name__)
CARD_SIZE = (1200, 630)
AVATAR_SIZE = 112
LOGO_PATH = Path(__file__).parent / "assets" / "grindpvp-icon.png"
RANK_COLORS = ("#f0b547", "#c5d0dc", "#c98959")


@lru_cache(maxsize=1)
def _load_logo() -> Image.Image:
    with Image.open(LOGO_PATH) as logo:
        return logo.convert("RGBA")


@lru_cache(maxsize=128)
def _fetch_avatar(player_uuid: str) -> bytes | None:
    url = f"https://mc-heads.net/avatar/{quote(player_uuid, safe='')}/128"
    request = Request(url, headers={"User-Agent": "GrindPvP social preview"})
    try:
        with urlopen(request, timeout=1.5) as response:
            image_data = response.read(1_000_001)
    except (OSError, URLError) as error:
        LOGGER.warning("Could not fetch social preview avatar for %s: %s", player_uuid, error)
        return None

    if len(image_data) > 1_000_000:
        LOGGER.warning("Social preview avatar for %s exceeded the size limit.", player_uuid)
        return None
    return image_data


def _avatar_image(player_uuid: str) -> Image.Image | None:
    image_data = _fetch_avatar(player_uuid)
    if image_data is None:
        return None

    try:
        with Image.open(BytesIO(image_data)) as image:
            if image.width > 512 or image.height > 512:
                LOGGER.warning("Social preview avatar for %s had unexpected dimensions.", player_uuid)
                return None
            image.load()
            return image.convert("RGBA")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        LOGGER.warning("Could not decode social preview avatar for %s: %s", player_uuid, error)
        return None


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _draw_avatar(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    avatar: Image.Image | None,
    username: str,
    x: int,
    y: int,
    accent: str,
) -> None:
    if avatar is None:
        draw.rounded_rectangle(
            (x, y, x + AVATAR_SIZE, y + AVATAR_SIZE),
            radius=18,
            fill="#233345",
        )
        draw.text(
            (x + AVATAR_SIZE // 2, y + AVATAR_SIZE // 2),
            username[:1].upper(),
            font=_font(58),
            fill="#f3f6fa",
            anchor="mm",
        )
    else:
        avatar = avatar.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.NEAREST)
        mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, AVATAR_SIZE - 1, AVATAR_SIZE - 1),
            radius=18,
            fill=255,
        )
        image.paste(avatar, (x, y), mask)

    draw.rounded_rectangle(
        (x - 3, y - 3, x + AVATAR_SIZE + 3, y + AVATAR_SIZE + 3),
        radius=21,
        outline=accent,
        width=3,
    )


def render_leaderboard_card(entries: list[dict[str, object]]) -> bytes:
    image = Image.new("RGB", CARD_SIZE, "#0d1621")
    draw = ImageDraw.Draw(image)
    avatars: list[Image.Image | None] = []
    if entries:
        player_uuids = [str(entry["uuid"]) for entry in entries[:3]]
        with ThreadPoolExecutor(max_workers=len(player_uuids)) as executor:
            avatars = list(executor.map(_avatar_image, player_uuids))

    logo = _load_logo().resize((76, 76), Image.Resampling.LANCZOS)
    image.paste(logo, (64, 46), logo)
    draw.text((160, 51), "GRINDPVP", font=_font(38), fill="#f4f7fb")
    draw.text((162, 98), "LIVE OVERALL RANKINGS", font=_font(20), fill="#9eacbd")
    draw.rounded_rectangle((934, 57, 1136, 109), radius=18, fill="#162535")
    draw.ellipse((955, 76, 969, 90), fill="#f08c22")
    draw.text((982, 71), "UPDATED LIVE", font=_font(18), fill="#e2e8f0")

    draw.text((64, 169), "CURRENT TOP 3 PLAYERS", font=_font(30), fill="#f4f7fb")
    draw.text((66, 207), "Overall rankings across all GrindPvP kits", font=_font(18), fill="#9eacbd")

    card_width = 344
    card_height = 322
    card_top = 262
    card_gap = 20
    card_left = 66
    for index in range(3):
        x = card_left + index * (card_width + card_gap)
        accent = RANK_COLORS[index]
        draw.rounded_rectangle(
            (x, card_top, x + card_width, card_top + card_height),
            radius=20,
            fill="#142231",
            outline="#26394b",
            width=2,
        )
        draw.rounded_rectangle(
            (x + 20, card_top + 20, x + 96, card_top + 58),
            radius=13,
            fill="#1e3042",
        )
        draw.text(
            (x + 58, card_top + 39),
            f"#{index + 1}",
            font=_font(21),
            fill=accent,
            anchor="mm",
        )

        if index >= len(entries):
            draw.text(
                (x + card_width // 2, card_top + 146),
                "Awaiting player",
                font=_font(24),
                fill="#9eacbd",
                anchor="mm",
            )
            continue

        entry = entries[index]
        username = str(entry["username"])
        player_uuid = str(entry["uuid"])
        tier = str(entry["tier"])
        average_points = float(entry["average_points"])
        avatar_x = x + (card_width - AVATAR_SIZE) // 2
        _draw_avatar(image, draw, avatars[index], username, avatar_x, card_top + 72, accent)
        draw.text(
            (x + card_width // 2, card_top + 218),
            username,
            font=_font(28),
            fill="#f4f7fb",
            anchor="mm",
        )
        draw.text(
            (x + card_width // 2, card_top + 258),
            f"{tier}  ·  {average_points:.2f} AVG PTS",
            font=_font(18),
            fill=accent,
            anchor="mm",
        )

    draw.line((66, 608, 1136, 608), fill="#26394b", width=2)
    draw.text((66, 612), "grindpvp-blsu.onrender.com", font=_font(14), fill="#728398")

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
