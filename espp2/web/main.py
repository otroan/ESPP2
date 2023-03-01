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
from espp2.datamodels import ESPPResponse

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()


@app.post("/files/", response_model=ESPPResponse)
async def create_files(
        broker: str = Form(...),
        transfile1: UploadFile = File(...),
        transformat1: str = Form(...),
        transfile2: Optional[UploadFile] = None,
        transformat2: str = Form(""),
        holdfile: UploadFile | None = None,
        wirefile: UploadFile | None = None,
        year: int = Form(...)):
    '''File upload endpoint'''
    transaction_files = [
        {'name': transfile1.filename, 'format': transformat1, 'fd': transfile1.file}]

    if transfile2 and transfile2.filename != '':
        transaction_files.append(
            {'name': transfile2.filename, 'format': transformat2, 'fd': transfile2.file})
    if wirefile and wirefile.filename == '':
        wirefile = None
    elif wirefile:
        wirefile = wirefile.file
    if holdfile and holdfile.filename == '':
        holdfile = None
    elif holdfile:
        holdfile = holdfile.file
    try:
        report, holdings = do_taxes(
            broker, transaction_files, holdfile, wirefile, year)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    return ESPPResponse(tax_report=report, holdings=holdings)


app.mount("/", StaticFiles(directory=realpath(
    f'{realpath(__file__)}/../public'), html=True), name='public')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
