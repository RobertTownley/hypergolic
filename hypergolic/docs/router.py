from fastapi import APIRouter

from hypergolic.docs.operations import DocContent, DocEntry, list_doc_entries, read_doc_content

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.get("/list", response_model=list[DocEntry])
def list_docs():
    return list_doc_entries()


@router.get("/read/{slug}", response_model=DocContent)
def read_doc(slug: str):
    return read_doc_content(slug)
