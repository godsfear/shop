from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False,
                                      env_file=".env",
                                      env_file_encoding="utf-8",
                                      extra="ignore")
    server_host: str = '127.0.0.1'
    server_port: int = 8000
    database_uri: str = 'sqlite:///./database.sqlite3'
    jwt_algorithm: str = 'HS256'
    jwt_secret: str = ''
    jwt_expires_s: int = 3600
    sql_echo: bool = True
    api_prefix: str = '/api/v1'
    # ключевой сервис (заглушка HSM, см. keyservice.py)
    keyservice_dir: str = 'keyservice'
    breakglass_approvals: int = 2          # «правило двух»
    breakglass_role: str = 'keyholder'     # единственная роль подтверждающих
    veto_window_s: int = 7 * 24 * 3600     # окно вето recovery-заявки


settings = Settings()
