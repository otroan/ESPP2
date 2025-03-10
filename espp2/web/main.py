#!/usr/bin/env python3

"""
ESPP2 web server
"""
# pylint: disable=invalid-name

import logging
from io import StringIO
import json
import base64
from os.path import realpath
import uvicorn
from fastapi import FastAPI, Form, UploadFile, HTTPException
from pydantic import TypeAdapter
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from starlette.responses import FileResponse
from espp2.main import (
    do_taxes,
    get_zipdata,
    do_holdings,
)
from espp2.datamodels import ESPPResponse, Wires, Holdings

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger()

app = FastAPI()


def capture_logs_start() -> logging.StreamHandler:
    log_stream = StringIO()
    log_handler = logging.StreamHandler(log_stream)
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    return log_handler


def capture_logs_stop(log_handler) -> str:
    logger.removeHandler(log_handler)
    log_handler.flush()
    log_handler.stream.flush()
    return log_handler.stream.getvalue()


@app.post("/taxreport/", response_model=ESPPResponse)
async def taxreport(
    transaction_files: list[UploadFile],
    broker: str = Form(...),
    holdfile: UploadFile | None = None,
    wires: str = Form(""),
    #        opening_balance: str = Form(...),
    year: int = Form(...),
):
    log_handler = capture_logs_start()
    """File upload endpoint"""
    opening_balance = None
    if wires:
        wires_list = json.loads(wires)
        wires = Wires(root=wires_list)

    if opening_balance:
        adapter = TypeAdapter(Holdings)
        opening_balance = adapter.validate_json(opening_balance)

    if holdfile and holdfile.filename == "":
        holdfile = None
    elif holdfile:
        holdfile = holdfile.file
    try:
        report, holdings, exceldata, summary = do_taxes(
            broker, transaction_files, holdfile, wires, year, portfolio_engine=True
        )
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e)) from e

    zipdata = get_zipdata(
        [
            (
                f"espp-holdings-{year}.json",
                holdings.model_dump_json(indent=4),
            ),
            (f"espp-portfolio-{year}.xlsx", exceldata),
        ]
    )
    zipstr = jsonable_encoder(
        zipdata, custom_encoder={bytes: lambda v: base64.b64encode(v).decode("utf-8")}
    )
    logstr = capture_logs_stop(log_handler)
    return ESPPResponse(
        tax_report=report, holdings=holdings, zip=zipstr, summary=summary, log=logstr
    )

@app.post("/holdings", response_model=Holdings)
async def generate_holdings(
    transaction_files: list[UploadFile],
    broker: str = Form(...),
    year: int = Form(...),
):
    """Generate previous year holdings from a plethora of transaction files"""
    try:
        return do_holdings(
            broker, transaction_files, year)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# This seems to keep us from caching the files too agressively.
# Is there a simpler way to do cache control serverside?
# Might require e.g. an nginx proxy?


@app.get("/bundle.js")
async def get_bundle():
    logger.debug("bundle.js")
    return FileResponse(
        realpath(f"{realpath(__file__)}/../public/bundle.js"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


app.mount(
    "/",
    StaticFiles(directory=realpath(f"{realpath(__file__)}/../public"), html=True),
    name="public",
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
