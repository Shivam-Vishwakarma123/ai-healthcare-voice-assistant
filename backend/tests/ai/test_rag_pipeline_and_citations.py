from __future__ import annotations

from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.services.rag_service import RAGDocumentInput, RAGSearchResult, RAGService


@pytest.fixture
def test_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with session_factory() as db:
        yield db
    engine.dispose()


def test_rag_ingest_and_retrieval(test_db: Session):
    """Verify document ingestion, chunking, and cosine similarity retrieval."""
    service = RAGService()
    doc_input = RAGDocumentInput(
        title="WHO Hypertension Management Guidelines",
        source_url="https://www.who.int/news-room/fact-sheets/detail/hypertension",
        content=(
            "Hypertension (high blood pressure) is when the pressure in your blood vessels is too high (140/90 mmHg or higher). "
            "It is common but can be serious if not treated. People with high blood pressure may not feel any symptoms. "
            "Lifestyle modifications including reduced salt intake and physical activity help control blood pressure."
        ),
        version="1.0",
        licence="Open Access (WHO)",
        allowed_use="Public health education",
        provenance="World Health Organization",
        category="public_health",
    )
    doc = service.ingest_document(test_db, doc_input)
    assert doc.id is not None
    assert len(doc.chunks) >= 1

    # Search for hypertension
    hits = service.search(test_db, "high blood pressure symptoms", limit=3)
    assert len(hits) >= 1
    top_hit = hits[0]
    assert "Hypertension" in top_hit.title
    assert "https://www.who.int" in top_hit.source_url
    assert top_hit.score > 0


def test_citation_formatting_and_provenance():
    """Verify citations accurately link to verified source URLs with version and license."""
    hit = RAGSearchResult(
        title="MOHFW National Guidelines for Stroke",
        source_url="https://main.mohfw.gov.in/sites/default/files/StrokeGuidelines.pdf",
        licence="Government Open Data Licence - India (GODL)",
        allowed_use="Clinical education and triage reference",
        provenance="Ministry of Health and Family Welfare, Government of India",
        citation="MOHFW National Guidelines for Stroke (v2.1)",
        snippet="Immediate recognition of stroke signs using FAST methodology reduces morbidity.",
        publication_date="2023-01-15T00:00:00+00:00",
        updated_at="2024-02-01T00:00:00+00:00",
        retrieval_date=datetime.now(timezone.utc).isoformat(),
        version="2.1",
        score=0.88,
    )
    context = RAGService.build_context_from_hits([hit])
    assert "MOHFW National Guidelines for Stroke" in context
    assert "https://main.mohfw.gov.in" in context
    assert "FAST methodology" in context


def test_conflict_detection_in_rag_sources():
    """Verify source conflict detector flags contradictory emergency instructions."""
    # Non-conflicting hits
    hits_normal = [
        RAGSearchResult(
            title="Guideline A",
            source_url="https://www.who.int/a",
            licence="Open",
            allowed_use="Education",
            provenance="WHO",
            citation="A",
            snippet="Drink water and rest.",
            publication_date=None,
            updated_at=None,
            retrieval_date=datetime.now(timezone.utc).isoformat(),
            version="1.0",
            score=0.9,
        )
    ]
    assert not RAGService.sources_conflict(hits_normal)

    # Conflicting hits: one recommends emergency care, another advises against emergency care
    hits_conflict = [
        RAGSearchResult(
            title="Guideline Emergency",
            source_url="https://www.who.int/emergency",
            licence="Open",
            allowed_use="Education",
            provenance="WHO",
            citation="Emergency",
            snippet="In acute situations, seek emergency care immediately.",
            publication_date=None,
            updated_at=None,
            retrieval_date=datetime.now(timezone.utc).isoformat(),
            version="1.0",
            score=0.9,
        ),
        RAGSearchResult(
            title="Guideline Home",
            source_url="https://www.who.int/home",
            licence="Open",
            allowed_use="Education",
            provenance="WHO",
            citation="Home",
            snippet="For mild presentation, do not seek emergency care; rest at home.",
            publication_date=None,
            updated_at=None,
            retrieval_date=datetime.now(timezone.utc).isoformat(),
            version="1.0",
            score=0.85,
        ),
    ]
    assert RAGService.sources_conflict(hits_conflict)
