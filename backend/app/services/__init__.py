"""Domain services: pure(ish) functions over a SQLAlchemy `Session`, with no
FastAPI/HTTP concerns. Routers call these and map the result onto a schema;
the services never import from `app.routers` or FastAPI itself.
"""
