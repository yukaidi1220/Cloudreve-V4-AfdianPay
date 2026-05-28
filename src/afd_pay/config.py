from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，所有参数从环境变量或 .env 文件读取"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # ========== Cloudreve 配置 ==========
    site_url: str = ""
    communication_key: str = ""

    # ========== 爱发电配置 ==========
    afdian_user_id: str = ""
    afdian_token: str = ""

    # ========== 服务配置 ==========
    port: int = 5000
    log_level: str = "INFO"

    # ========== 自定义 User-Agent ==========
    user_agent_cloudreve: str = "AfdPay"
    user_agent_afdian: str = "AfdPay"

    # ========== 可选配置 ==========
    db_path: str = "data/afdian_pay.db"
    afdian_api_base: str = "https://ifdian.net"
    afdian_api_fallback: str = "https://afdian.com"
    afdian_payment_base: str = "https://ifdian.net"
    min_amount_fen: int = 500
    notify_max_attempts: int = 20
    notify_base_delay: float = 5.0
    notify_max_delay: float = 1800.0

    def validate_required(self) -> list[str]:
        """返回缺失的必填项列表，为空则表示全部通过"""
        missing = []
        if not self.site_url.strip():
            missing.append("SITE_URL")
        if not self.communication_key.strip():
            missing.append("COMMUNICATION_KEY")
        if not self.afdian_user_id.strip():
            missing.append("AFDIAN_USER_ID")
        if not self.afdian_token.strip():
            missing.append("AFDIAN_TOKEN")
        return missing
