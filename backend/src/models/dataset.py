from sqlalchemy import String, JSON, Double, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Dataset(Base):
    __tablename__ = 'datasets'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    source: Mapped[str] = mapped_column(String(200), default='manual.json')
    records: Mapped[list] = mapped_column(JSON)
    revisions: Mapped[dict] = mapped_column(JSON, default=dict)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Double)
    supplement_count: Mapped[int] = mapped_column(Integer, default=0)
class DatasetSupplement(Base):
    __tablename__ = 'dataset_supplements'
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    source: Mapped[str] = mapped_column(String(200), default='manual.json')
    uploaded_rows: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='applied')
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(150), default='')
    created_at: Mapped[float] = mapped_column(Double)
