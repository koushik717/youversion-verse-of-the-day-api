from pydantic import BaseModel


class VerseOfTheDay(BaseModel):
    day: int
    reference: str
    text: str
    version_id: int


class BibleVersion(BaseModel):
    id: int
    abbreviation: str
    title: str
