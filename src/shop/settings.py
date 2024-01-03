from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    server_host: str = '127.0.0.1'
    server_port: int = 8000
    database_uri: str = 'sqlite:///./database.sqlite3'
    jwt_algorithm: str = 'HS256'
    jwt_secret: str = ''
    jwt_expires_s: int = 3600
    sql_echo: bool = True


settings = Settings(
    _env_file='.env',
    _env_file_encoding='utf-8',
)
