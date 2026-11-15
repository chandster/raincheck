import calendar
import math
import os
import pandas as pd

from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

load_dotenv()
METEOMATICS_URL = "https://api.meteomatics.com"
LOCATION = (54.7023545, -3.2765753)


def _sum_rainfall_mm(response_data: dict[str, Any]) -> tuple[float, int]:
    try:
        coordinates = response_data["data"][0]["coordinates"]
    except (KeyError, IndexError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Rainfall provider returned an unexpected response",
        ) from exc

    coordinate = coordinates[0]
    dates = coordinate.get("dates") if isinstance(coordinate, dict) else None

    if not isinstance(dates, list) or not dates:
        raise HTTPException(
            status_code=502,
            detail="Rainfall provider returned no rainfall readings",
        )

    total = 0.0
    for reading in dates:
        try:
            value = reading["value"]
            if isinstance(value, bool):
                raise ValueError
            rainfall = float(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=502,
                detail="Rainfall provider returned an invalid rainfall reading",
            ) from exc
        if not math.isfinite(rainfall):
            raise HTTPException(
                status_code=502,
                detail="Rainfall provider returned an invalid rainfall reading",
            )
        total += rainfall
        print("total " + str(total))

    return (total, len(dates))


async def request_rainfall(start: datetime, end: datetime) -> tuple[float, int]:
    authorization = os.getenv("METEOMATICS_AUTHORIZATION")
    if not authorization:
        raise HTTPException(
            status_code=503,
            detail="METEOMATICS_AUTHORIZATION is not configured",
        )

    start_text = start.isoformat(timespec="milliseconds")
    end_text = end.isoformat(timespec="milliseconds")
    location_text = f"{LOCATION[0]},{LOCATION[1]}"
    url = (
        f"{METEOMATICS_URL}/{start_text}--{end_text}:P1D/"
        f"precip_24h:mm/{location_text}/json"
    )
    params = {"model": "mix"}

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.get(
                url,
                params=params,
                headers={"Authorization": authorization},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Rainfall provider returned HTTP {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to the rainfall provider",
        ) from exc

    try:
        response_data = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Rainfall provider returned invalid JSON",
        ) from exc
    if not isinstance(response_data, dict):
        raise HTTPException(
            status_code=502,
            detail="Rainfall provider returned an unexpected response",
        )

    return _sum_rainfall_mm(response_data)


async def get_monthly_rainfall(
    year: int | None = None,
    month: int | None = None,
) -> dict[str, int | list[dict[str, float]]]:
    now = datetime.now(timezone.utc)
    if (year is None) != (month is None):
        raise HTTPException(
            status_code=422,
            detail="Year and month must be provided together",
        )
    if year is None:
        year = now.year
        month = now.month
    if (year, month) > (now.year, now.month):
        raise HTTPException(
            status_code=422,
            detail="Rainfall is not available for a future month",
        )

    start = datetime(year, month, 1, tzinfo=timezone.utc)
    days_in_month = calendar.monthrange(year, month)[1]
    if (year, month) == (now.year, now.month):
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        end = start.replace(day=days_in_month)

    observed_rainfall, observed_days = await request_rainfall(start, end)

    if observed_days < days_in_month:
        print("rounding")
        rainfall = days_in_month / observed_days * observed_rainfall 
    else:
        print("not rounding")
        rainfall = observed_rainfall

    locations = [
        {
            "latitude": LOCATION[0],
            "longitude": LOCATION[1],
            "rainfall_mm": round(
                rainfall,
                2,
            ),
        }
    ]

    return {
        "year": year,
        "month": month,
        "locations": locations,
    }


@app.get("/rainfall")
async def monthly_rainfall(
    year: int | None = Query(default=None, ge=1900),
    month: int | None = Query(default=None, ge=1, le=12),
) -> dict[str, int | list[dict[str, float]]]:
    return await get_monthly_rainfall(year, month)

@app.get("/locations")
async def locations() -> list[list[float]]:
    locations_csv_path = Path(__file__).parent / "data" / "unique_locations.csv"
    locations_df = pd.read_csv(locations_csv_path)
    locations_rows = locations_df[["LAT", "LON"]].astype(float).values.tolist()
    return locations_rows

@app.get("/power-data")
async def power_data(
    year: int = Query(ge=1984, le=2025),
    month: int = Query(ge=1, le=12),
) -> list[dict[str, float | None]]:
    month_column = (
        "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
    )[month - 1]
    power_data_path = Path(__file__).parent / "data" / "POWER_Regional_Monthly_1984_2025.csv"
    power_df = pd.read_csv(
        power_data_path,
        skiprows=9,
        usecols=["YEAR", "LAT", "LON", month_column],
    )
    readings = power_df.loc[power_df["YEAR"] == year, ["LAT", "LON", month_column]]

    return [
        {
            "latitude": float(row.LAT),
            "longitude": float(row.LON),
            "value": None if row[month_column] == -999 else float(row[month_column]),
        }
        for _, row in readings.iterrows()
    ]
