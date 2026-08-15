from bifrostnms.config import get_settings

settings = get_settings()

TORTOISE_ORM = {
    "connections": {"default": settings.database_url},
    "apps": {
        "models": {
            "models": ["bifrostnms.models"],
            "default_connection": "default",
            "migrations": "bifrostnms.migrations",
        }
    },
}
