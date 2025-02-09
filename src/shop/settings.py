from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False,
                                      env_file=".env",
                                      env_file_encoding="utf-8")
    server_host: str = '127.0.0.1'
    server_port: int = 8000
    database_uri: str = 'sqlite:///./database.sqlite3'
    jwt_algorithm: str = 'HS256'
    jwt_secret: str = ''
    jwt_expires_s: int = 3600
    sql_echo: bool = True
    api_prefix: str = '/api/v1'


settings = Settings()
