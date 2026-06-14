"""Secondary service installer/image binary blob model."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, LargeBinary
from app.database import Base


class SecondaryServiceBlob(Base):
    """Stores the latest images/installers for secondary services as binary blobs.

    Allows offline installation and setup by caching remote installer packages or
    exported Docker image tarballs inside the database.
    """
    __tablename__ = "secondary_service_blobs"

    id             = Column(Integer, primary_key=True, index=True)
    service_key    = Column(String(64), unique=True, nullable=False, index=True)
    filename       = Column(String(256), nullable=False)
    blob_data      = Column(LargeBinary, nullable=False)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
