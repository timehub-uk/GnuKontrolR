"""AI provider credential storage — encrypted API keys per user."""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from app.database import Base


class AiProviderName(str, enum.Enum):
    anthropic        = "anthropic"
    openai           = "openai"
    zen              = "zen"
    ollama           = "ollama"
    opencode_account = "opencode_account"


class AiProvider(Base):
    __tablename__ = "ai_providers"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider       = Column(SAEnum(AiProviderName, name="aiprovidername"), nullable=False)
    api_key_enc    = Column(Text, nullable=True, default=None)  # Fernet-encrypted; OLLAMA_HOST for ollama
    default_model  = Column(String(64), default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_ai_provider_user"),)
