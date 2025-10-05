from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field

from swsc_core import DataStore, Entry, Race

app = FastAPI(title="SWSC Race Results API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FIN_CODES = ["", "DNF", "DNC", "OCS", "RET", "DSQ"]

logger = logging.getLogger(__name__)


class RaceMetadata(BaseModel):
    series: str
    race: str
    race_officer: str = Field(alias="raceOfficer")
    date: dt.date
    race_number: Optional[int] = Field(default=None, alias="raceNumber")
    start_time: Optional[dt.time] = Field(default=None, alias="startTime")

    model_config = ConfigDict(populate_by_name=True)

    def filename(self) -> str:
        raw = f"{self.series}_{self.race}_{self.race_officer}_{self.date.strftime('%d-%m-%Y')}"
        return re.sub(r"[^-\w]+", "_", raw)


class EntryPayload(BaseModel):
    entry_id: Optional[str] = Field(default=None, description="Entry ID (auto-generated if not provided)")
    helm: str
    crew: str
    dinghy: str
    sail_number: Optional[str] = Field(default=None, alias="sailNumber")
    personal: int = Field(default=0, description="Personal handicap (0 = no personal handicap)")
    laps: Optional[int] = None
    time_seconds: Optional[int] = Field(default=None, alias="timeSeconds", ge=0)
    code: Optional[str] = Field(default=None, alias="finCode")

    model_config = ConfigDict(populate_by_name=True)


class PyRowModel(BaseModel):
    entry_id: str = Field(alias="entryId")
    helm: str
    crew: str
    dinghy: str
    py: int
    laps: int
    time_seconds: int = Field(alias="timeSeconds")
    corrected: Optional[int]
    rank: Optional[float]
    fin_code: str = Field(default="", alias="finCode")

    model_config = ConfigDict(populate_by_name=True)


class PersonalRowModel(BaseModel):
    entry_id: str = Field(alias="entryId")
    helm: str
    crew: str
    personal_handicap: int = Field(alias="personalHandicap")
    corrected: Optional[int]
    rank: Optional[float]

    model_config = ConfigDict(populate_by_name=True)


class ScoreMetadataResponse(BaseModel):
    series: str
    race: str
    race_number: Optional[int] = Field(default=None, alias="raceNumber")
    race_officer: str = Field(alias="raceOfficer")
    date: str
    start_time: Optional[str] = Field(default=None, alias="startTime")
    filename: str
    generated_at: str = Field(alias="generatedAt")

    model_config = ConfigDict(populate_by_name=True)


class ScoreResponse(BaseModel):
    metadata: ScoreMetadataResponse
    py_results: List[PyRowModel] = Field(alias="pyResults")
    personal_results: List[PersonalRowModel] = Field(alias="personalResults")
    summary: str
    html: str

    model_config = ConfigDict(populate_by_name=True)


class ScheduledRaceCreate(BaseModel):
    series: str
    race: str
    race_number: Optional[int] = Field(default=None, alias="raceNumber")
    date: dt.date
    start_time: Optional[dt.time] = Field(default=None, alias="startTime")
    race_officer: Optional[str] = Field(default=None, alias="raceOfficer")
    notes: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class ScheduledRaceResponseModel(BaseModel):
    id: str
    series: str
    race: str
    series_code: Optional[str] = Field(default=None, alias="seriesCode")
    race_number: Optional[int] = Field(default=None, alias="raceNumber")
    date: str
    start_time: Optional[str] = Field(default=None, alias="startTime")
    race_officer: Optional[str] = Field(default=None, alias="raceOfficer")
    notes: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class ScheduledRaceListResponse(BaseModel):
    races: List[ScheduledRaceResponseModel]


class SeriesCreatePayload(BaseModel):
    title: str
    code: Optional[str] = None
    start_date: Optional[dt.date] = Field(default=None, alias="startDate")
    end_date: Optional[dt.date] = Field(default=None, alias="endDate")

    model_config = ConfigDict(populate_by_name=True)


class SeriesUpdatePayload(BaseModel):
    title: Optional[str] = None
    start_date: Optional[dt.date] = Field(default=None, alias="startDate")
    end_date: Optional[dt.date] = Field(default=None, alias="endDate")

    model_config = ConfigDict(populate_by_name=True)


class SeriesResponseModel(BaseModel):
    id: str
    code: str
    title: str
    start_date: Optional[str] = Field(default=None, alias="startDate")
    end_date: Optional[str] = Field(default=None, alias="endDate")

    model_config = ConfigDict(populate_by_name=True)


class SeriesListResponse(BaseModel):
    series: List[SeriesResponseModel]


class SeriesScoreCell(BaseModel):
    value: Optional[float] = None
    counted: bool
    is_dnc: bool = Field(alias="isDnc")

    model_config = ConfigDict(populate_by_name=True)


class SeriesScoreSummary(BaseModel):
    per_race: List[SeriesScoreCell] = Field(alias="perRace")
    total: Optional[float] = None

    model_config = ConfigDict(populate_by_name=True)


class SeriesRaceSummary(BaseModel):
    id: str
    label: str
    race_number: Optional[int] = Field(default=None, alias="raceNumber")
    date: Optional[str] = None
    start_time: Optional[str] = Field(default=None, alias="startTime")

    model_config = ConfigDict(populate_by_name=True)


class SeriesStandingsSeriesModel(BaseModel):
    id: str
    code: str
    title: str
    start_date: Optional[str] = Field(default=None, alias="startDate")
    end_date: Optional[str] = Field(default=None, alias="endDate")
    to_count: int = Field(alias="toCount")
    count_all: bool = Field(alias="countAll")
    race_count: int = Field(alias="raceCount")
    competitor_count: int = Field(alias="competitorCount")
    dnc_value: int = Field(alias="dncValue")

    model_config = ConfigDict(populate_by_name=True)


class SeriesCompetitorScores(BaseModel):
    helm: str
    boats: List[str]
    crews: List[str]
    scores: SeriesScoreSummary
    rank: Optional[int] = None

    model_config = ConfigDict(populate_by_name=True)


class SeriesStandingsResponse(BaseModel):
    series: SeriesStandingsSeriesModel
    races: List[SeriesRaceSummary]
    py_results: List[SeriesCompetitorScores] = Field(alias="pyResults")
    personal_results: List[SeriesCompetitorScores] = Field(alias="personalResults")

    model_config = ConfigDict(populate_by_name=True)


class PortalCrewMemberModel(BaseModel):
    profile_id: Optional[str] = Field(default=None, alias="profileId")
    name: str

    model_config = ConfigDict(populate_by_name=True)


class SeriesEntryRequestItem(BaseModel):
    series_id: str = Field(alias="seriesId")
    helm_profile_id: Optional[str] = Field(default=None, alias="helmProfileId")
    helm_name: str = Field(alias="helmName")
    crew: List[PortalCrewMemberModel] = Field(default_factory=list)
    boat_class: Optional[str] = Field(default=None, alias="boatClass")
    sail_number: Optional[str] = Field(default=None, alias="sailNumber")
    notes: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class SeriesEntryCreateRequest(BaseModel):
    entries: List[SeriesEntryRequestItem] = Field(min_length=1)


class SeriesSummaryModel(BaseModel):
    id: str
    code: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = Field(default=None, alias="startDate")
    end_date: Optional[str] = Field(default=None, alias="endDate")

    model_config = ConfigDict(populate_by_name=True)


class SeriesEntryRecordModel(BaseModel):
    id: str
    series: SeriesSummaryModel
    helm_name: str = Field(alias="helmName")
    helm_profile_id: Optional[str] = Field(default=None, alias="helmProfileId")
    crew: List[PortalCrewMemberModel]
    boat_class: Optional[str] = Field(default=None, alias="boatClass")
    sail_number: Optional[str] = Field(default=None, alias="sailNumber")
    notes: Optional[str] = None
    submitted_by: Optional[str] = Field(default=None, alias="submittedBy")
    created_at: str = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class SeriesEntryCreateResponse(BaseModel):
    entries: List[SeriesEntryRecordModel]


class RaceSummaryModel(BaseModel):
    id: str
    label: str
    date: str
    start_time: Optional[str] = Field(default=None, alias="startTime")
    race_number: Optional[int] = Field(default=None, alias="raceNumber")

    model_config = ConfigDict(populate_by_name=True)


class RaceSignonRecordModel(BaseModel):
    id: str
    series: SeriesSummaryModel
    race: RaceSummaryModel
    helm_name: str = Field(alias="helmName")
    helm_profile_id: Optional[str] = Field(default=None, alias="helmProfileId")
    crew: List[PortalCrewMemberModel]
    boat_class: Optional[str] = Field(default=None, alias="boatClass")
    sail_number: Optional[str] = Field(default=None, alias="sailNumber")
    notes: Optional[str] = None
    submitted_by: Optional[str] = Field(default=None, alias="submittedBy")
    created_at: str = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


class RaceSignonRequestModel(BaseModel):
    series_id: str = Field(alias="seriesId")
    scheduled_race_ids: List[str] = Field(alias="scheduledRaceIds", min_length=1)
    helm_profile_id: Optional[str] = Field(default=None, alias="helmProfileId")
    helm_name: str = Field(alias="helmName")
    crew: List[PortalCrewMemberModel] = Field(default_factory=list)
    boat_class: Optional[str] = Field(default=None, alias="boatClass")
    sail_number: Optional[str] = Field(default=None, alias="sailNumber")
    notes: Optional[str] = None
    signon_date: Optional[str] = Field(default=None, alias="signonDate")

    model_config = ConfigDict(populate_by_name=True)


class RaceSignonResponseModel(BaseModel):
    signons: List[RaceSignonRecordModel]


class ProfileBoatModel(BaseModel):
    class_name: str = Field(default="", alias="className")
    sail_number: Optional[str] = Field(default=None, alias="sailNumber")

    model_config = ConfigDict(populate_by_name=True)


class ProfileRosterModel(BaseModel):
    id: str
    helm: str
    crew: Optional[str] = None
    boats: List[ProfileBoatModel] = Field(default_factory=list)


class ProfileRosterResponse(BaseModel):
    profiles: List[ProfileRosterModel]


@lru_cache(maxsize=1)
def store() -> DataStore:
    return DataStore()


def require_user(authorization: str = Header(default="")) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization token is required")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token is required")

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_anon_key:
        raise HTTPException(status_code=500, detail="Supabase configuration is incomplete")

    endpoint = f"{supabase_url}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": supabase_anon_key,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(endpoint, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response else 502
        if status in (401, 403):
            raise HTTPException(status_code=401, detail="Invalid authentication token") from exc
        raise HTTPException(status_code=502, detail="Failed to verify authentication token") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Failed to verify authentication token") from exc

    user_id = str(payload.get("id") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    payload["id"] = user_id
    return payload


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/reference")
def reference() -> dict:
    classes = store().load_handicaps()
    return {
        "classes": classes,
        "classOptions": [
            {"key": key, "label": label}
            for key, label in store().class_display_options()
        ],
        "finCodes": FIN_CODES,
    }


@app.get("/scheduled-races", response_model=ScheduledRaceListResponse)
def scheduled_races(includePast: bool = Query(default=False, alias="includePast")):
    try:
        races = store().fetch_scheduled_races(include_past=includePast)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ScheduledRaceListResponse(races=[ScheduledRaceResponseModel(**race) for race in races])


@app.post("/scheduled-races", response_model=ScheduledRaceResponseModel, status_code=201)
def create_scheduled_race(payload: ScheduledRaceCreate):
    try:
        record = store().create_scheduled_race(payload.dict(by_alias=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ScheduledRaceResponseModel(**record)


@app.get("/series", response_model=SeriesListResponse)
def list_series():
    try:
        series = store().fetch_series()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SeriesListResponse(series=[SeriesResponseModel(**item) for item in series])


@app.post("/series", response_model=SeriesResponseModel, status_code=201)
def create_series(payload: SeriesCreatePayload):
    try:
        record = store().create_series(payload.dict(by_alias=True, exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SeriesResponseModel(**record)


@app.get("/series/{series_id}/standings", response_model=SeriesStandingsResponse)
def series_standings(series_id: str):
    try:
        standings = store().fetch_series_standings(series_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SeriesStandingsResponse(**standings)


@app.post("/portal/series-entries", response_model=SeriesEntryCreateResponse)
def portal_series_entries(payload: SeriesEntryCreateRequest, user: Dict[str, Any] = Depends(require_user)):
    try:
        prepared_entries = [item.model_dump(by_alias=True, exclude_unset=True) for item in payload.entries]
        records = store().create_series_entries(user, prepared_entries)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SeriesEntryCreateResponse(entries=[SeriesEntryRecordModel(**record) for record in records])


@app.post("/portal/signons", response_model=RaceSignonResponseModel)
def portal_signons(payload: RaceSignonRequestModel, user: Dict[str, Any] = Depends(require_user)):
    try:
        payload_dict = payload.model_dump(by_alias=True, exclude_unset=True)
        records = store().create_race_signons(user, payload_dict)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RaceSignonResponseModel(signons=[RaceSignonRecordModel(**record) for record in records])


@app.get("/profiles-roster", response_model=ProfileRosterResponse)
def profiles_roster():
    roster = store().fetch_profiles_roster()
    return ProfileRosterResponse(profiles=[ProfileRosterModel(**item) for item in roster])


@app.patch("/series/{series_id}", response_model=SeriesResponseModel)
def update_series(series_id: str, payload: SeriesUpdatePayload):
    try:
        record = store().update_series(series_id, payload.dict(by_alias=True, exclude_unset=True))
    except ValueError as exc:
        if str(exc) == "Series not found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SeriesResponseModel(**record)


class ScoreRequest(BaseModel):
    metadata: RaceMetadata
    entries: List[EntryPayload]


@app.post("/score", response_model=ScoreResponse)
def score(payload: ScoreRequest):
    metadata = payload.metadata
    entries_payload = payload.entries
    classes = store().load_handicaps()

    # Entry ID tracking within series
    entry_id_map: Dict[str, str] = {}  # (helm, crew, dinghy) -> entry_id
    next_entry_num = 1

    race_entries: List[Entry] = []
    persist_entries: List[dict] = []

    for item in entries_payload:
        fin_code = (item.code or "").upper()
        if fin_code and fin_code not in FIN_CODES:
            raise HTTPException(status_code=400, detail=f"Unknown finish code '{fin_code}'")
        
        dinghy = item.dinghy.strip().upper()
        if dinghy not in classes:
            raise HTTPException(status_code=400, detail=f"Unknown dinghy class '{item.dinghy}'")

        sail_number = (item.sail_number or "").strip()

        # Generate or reuse entry_id
        if item.entry_id:
            entry_id = item.entry_id
        else:
            # Create unique key for this competitor
            key = f"{item.helm.strip()}|{item.crew.strip()}|{dinghy}"
            if key in entry_id_map:
                entry_id = entry_id_map[key]
            else:
                # Generate entry ID from series name and sequence number
                series_prefix = re.sub(r"[^A-Z0-9]+", "", metadata.series.upper())[:4]
                entry_id = f"{series_prefix}{next_entry_num:03d}"
                entry_id_map[key] = entry_id
                next_entry_num += 1

        laps = item.laps or 0
        time_seconds = item.time_seconds or 0

        race_entries.append(
            Entry(
                entry_id=entry_id,
                helm=item.helm.strip(),
                crew=item.crew.strip(),
                dinghy=dinghy,
                py=classes[dinghy],
                personal=item.personal,
                laps=laps,
                time_seconds=time_seconds,
                fin_code=fin_code,
                sail_number=sail_number,
            )
        )

        persist_entries.append(
            {
                "entry_id": entry_id,
                "helm": item.helm.strip(),
                "crew": item.crew.strip(),
                "dinghy": dinghy,
                "py": classes[dinghy],
                "personal": item.personal,
                "laps": laps,
                "time_seconds": time_seconds,
                "fin_code": fin_code,
                "sail_number": sail_number,
            }
        )

    race = Race(entries=race_entries)
    results = race.score()

    start_time_str = metadata.start_time.isoformat() if metadata.start_time else None

    response = ScoreResponse(
        metadata=ScoreMetadataResponse(
            series=metadata.series,
            race=metadata.race,
            raceNumber=metadata.race_number,
            race_officer=metadata.race_officer,
            date=metadata.date.isoformat(),
            startTime=start_time_str,
            filename=metadata.filename(),
            generated_at=dt.datetime.utcnow().isoformat() + "Z",
        ),
        pyResults=[
            PyRowModel(
                entryId=row.entry_id,
                helm=row.helm,
                crew=row.crew,
                dinghy=row.dinghy,
                py=row.py,
                laps=row.laps,
                timeSeconds=row.time_seconds,
                corrected=row.corrected,
                rank=row.rank,
                finCode=row.fin_code,
            )
            for row in results.py_rows
        ],
        personalResults=[
            PersonalRowModel(
                entryId=row.entry_id,
                helm=row.helm,
                crew=row.crew,
                personalHandicap=row.personal_handicap,
                corrected=row.corrected,
                rank=row.rank,
            )
            for row in results.personal_rows
        ],
        summary=results.summary_text,
        html=results.html,
    )

    try:
        metadata_json = jsonable_encoder(metadata, by_alias=True)
        request_payload = jsonable_encoder(payload, by_alias=True)
        response_payload = jsonable_encoder(response, by_alias=True)
        store().persist_race(metadata_json, request_payload, response_payload, persist_entries)
    except Exception:
        logger.exception("Failed to persist race data to Supabase")
    return response
