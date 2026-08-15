from datetime import date

from pydantic import BaseModel, ConfigDict


class TermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    term_id: int
    term_code: str
    academic_year: int
    term_type: str
    sequence_index: int
    start_date: date | None = None
    end_date: date | None = None
