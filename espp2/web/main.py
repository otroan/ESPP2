#!/usr/bin/env python3

'''
ESPP2 web server
'''
# pylint: disable=invalid-name

import logging
from typing import Optional
from os.path import realpath
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from espp2.main import do_taxes
from espp2.datamodels import ESPPResponse, WireAmount

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.post("/files/", response_model=ESPPResponse)
async def create_files(
        transaction_files: list[UploadFile],
        broker: str = Form(...),
        holdfile: UploadFile | None = None,
        wires: list[WireAmount] | None = None,
        year: int = Form(...)):

    '''File upload endpoint'''
    if holdfile and holdfile.filename == '':
        holdfile = None
    elif holdfile:
        holdfile = holdfile.file
    try:
        report, holdings = do_taxes(
            broker, transaction_files, holdfile, wires, year)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    return ESPPResponse(tax_report=report, holdings=holdings)


app.mount("/", StaticFiles(directory=realpath(
    f'{realpath(__file__)}/../public'), html=True), name='public')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
