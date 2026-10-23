import hashlib
import difflib
import tempfile
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.store import database, Version, Node, Selection, Generation
from app.parser import parse_pdf


class SelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    version: str
    node_ids: list[str] = Field(min_length=1, max_length=100)


def create_app(url=None):
    app = FastAPI(title="CT-200 Versioned QA Backend", version="1.0.0")
    app.state.sessions = database(url)

    def required(s, model, ident):
        obj = s.get(model, ident)
        if obj is None:
            raise HTTPException(404, f"{model.__name__} not found")
        return obj

    def nodes(s, version):
        required(s, Version, version)
        return {
            n.key: n for n in s.scalars(select(Node).where(Node.version == version))
        }

    def node_json(n):
        return dict(id=n.id, version=n.version, **n.data)

    def generation_json(s, g, against=None):
        doc = dict(g.document)
        target = (
            against or s.scalar(select(Version).order_by(Version.sequence.desc())).id
        )
        current = nodes(s, target)
        changes = [
            x["key"]
            for x in doc["sources"]
            if x["key"] not in current or current[x["key"]].data["hash"] != x["hash"]
        ]
        return dict(
            id=g.id,
            selection_id=g.selection_id,
            **doc,
            against_version=target,
            stale=bool(changes),
            changed_source_keys=changes,
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/versions/{version}", status_code=201)
    async def ingest(
        version: str, file: UploadFile = File(...), force_ocr: bool = False
    ):
        if not version or len(version) > 40 or ":" in version:
            raise HTTPException(422, "Invalid version label")
        content = await file.read(20 * 1024 * 1024 + 1)
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(413, "Maximum PDF size is 20 MiB")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(422, "Expected PDF")
        with app.state.sessions() as s:
            if s.get(Version, version):
                raise HTTPException(409, "Versions are immutable")
            try:
                with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                    tmp.write(content)
                    tmp.flush()
                    parsed, warnings = parse_pdf(tmp.name, force_ocr)
            except Exception as exc:
                raise HTTPException(
                    422, f"PDF extraction failed: {type(exc).__name__}"
                ) from exc
            sequence = (s.scalar(select(func.max(Version.sequence))) or 0) + 1
            s.add(
                Version(
                    id=version,
                    sequence=sequence,
                    file_hash=hashlib.sha256(content).hexdigest(),
                    warnings=warnings,
                )
            )
            for n in parsed:
                s.add(
                    Node(
                        id=f'{version}:{n["key"]}',
                        version=version,
                        key=n["key"],
                        data=n,
                    )
                )
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                raise HTTPException(409, "Concurrent version import; retry")
            return {"version": version, "nodes": len(parsed), "warnings": warnings}

    @app.get("/versions")
    def versions():
        with app.state.sessions() as s:
            return [
                dict(
                    version=v.id,
                    sequence=v.sequence,
                    file_hash=v.file_hash,
                    warnings=v.warnings,
                )
                for v in s.scalars(select(Version).order_by(Version.sequence))
            ]

    @app.get("/versions/{version}/sections")
    def sections(version: str, parent: str = "root"):
        with app.state.sessions() as s:
            ns = nodes(s, version)
            if parent not in ns:
                raise HTTPException(404, "Parent not found")
            return [node_json(n) for n in ns.values() if n.data["parent"] == parent]

    @app.get("/nodes/{node_id}")
    def node(node_id: str):
        with app.state.sessions() as s:
            n = required(s, Node, node_id)
            return dict(
                **node_json(n),
                children=[
                    x.id
                    for x in nodes(s, n.version).values()
                    if x.data["parent"] == n.key
                ],
            )

    @app.get("/search")
    def search(
        version: str,
        q: str = Query(min_length=1),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        with app.state.sessions() as s:
            matches = [
                node_json(n)
                for n in nodes(s, version).values()
                if q.casefold() in (n.data["title"] + " " + n.data["text"]).casefold()
            ]
            return {"total": len(matches), "items": matches[offset : offset + limit]}

    @app.get("/diff")
    def diff(from_version: str, to_version: str):
        with app.state.sessions() as s:
            a, b = nodes(s, from_version), nodes(s, to_version)
            result = []
            for key in sorted(a.keys() | b.keys()):
                old, new = a.get(key), b.get(key)
                if old and new and old.data["hash"] == new.data["hash"]:
                    continue
                before = old.data["full_text"] if old else ""
                after = new.data["full_text"] if new else ""
                result.append(
                    dict(
                        key=key,
                        status=(
                            "added" if not old else "removed" if not new else "modified"
                        ),
                        before=before,
                        after=after,
                        diff="\n".join(
                            difflib.unified_diff(
                                before.split(), after.split(), lineterm=""
                            )
                        ),
                    )
                )
            return result

    @app.post("/selections", status_code=201)
    def save_selection(body: SelectionInput):
        with app.state.sessions() as s:
            ns = nodes(s, body.version)
            ids = list(dict.fromkeys(body.node_ids))
            if any(i not in {n.id for n in ns.values()} for i in ids):
                raise HTTPException(422, "Every node must belong to the pinned version")
            obj = Selection(
                id=str(uuid.uuid4()),
                name=body.name.strip(),
                version=body.version,
                nodes=ids,
            )
            s.add(obj)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                raise HTTPException(409, "Selection name already exists")
            return dict(
                id=obj.id, name=obj.name, version=obj.version, node_ids=obj.nodes
            )

    @app.get("/selections/{selection_id}")
    def get_selection(selection_id: str):
        with app.state.sessions() as s:
            obj = required(s, Selection, selection_id)
            return dict(
                id=obj.id, name=obj.name, version=obj.version, node_ids=obj.nodes
            )

    @app.post("/selections/{selection_id}/generate", status_code=201)
    def generate(selection_id: str):
        from app.llm import generate_document, GenerationError

        with app.state.sessions() as s:
            sel = required(s, Selection, selection_id)
            sources = [node_json(required(s, Node, i)) for i in sel.nodes]
            try:
                doc = generate_document(sources)
            except GenerationError as exc:
                raise HTTPException(502, str(exc)) from exc
            g = Generation(id=str(uuid.uuid4()), selection_id=sel.id, document=doc)
            s.add(g)
            s.commit()
            return generation_json(s, g)

    @app.get("/generations")
    def generations(
        selection_id: str | None = None,
        node_id: str | None = None,
        stale: bool | None = None,
        against_version: str | None = None,
    ):
        with app.state.sessions() as s:
            if against_version:
                required(s, Version, against_version)
            if selection_id:
                required(s, Selection, selection_id)
            if node_id:
                required(s, Node, node_id)
            result = []
            for g in s.scalars(select(Generation)):
                if selection_id and g.selection_id != selection_id:
                    continue
                if node_id and node_id not in [x["id"] for x in g.document["sources"]]:
                    continue
                item = generation_json(s, g, against_version)
                if stale is None or item["stale"] == stale:
                    result.append(item)
            return result

    return app


app = create_app()
