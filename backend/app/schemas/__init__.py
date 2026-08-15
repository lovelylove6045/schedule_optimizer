"""Pydantic schemas for API request/response bodies.

Kept separate from `app.models` (the SQLAlchemy ORM classes) on purpose:
these shape what crosses the HTTP boundary, and shouldn't have to change in
lockstep with internal database columns, nor leak lazy-loaded ORM
relationships into a JSON response.
"""
