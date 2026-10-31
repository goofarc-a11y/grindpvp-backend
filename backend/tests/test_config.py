from app.config import Settings


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(cors_origins="https://grindpvp.example, http://localhost:5173,")

    assert settings.cors_origin_list == [
        "https://grindpvp-blsu.onrender.com",
        "https://grindpvp.example",
        "http://localhost:5173",
    ]


def test_default_website_origin_is_not_duplicated() -> None:
    settings = Settings(cors_origins="https://grindpvp-blsu.onrender.com")

    assert settings.cors_origin_list == ["https://grindpvp-blsu.onrender.com"]
