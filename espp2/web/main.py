#!/usr/bin/env python3

'''
ESPP2 web server
'''
# pylint: disable=invalid-name

import logging
from typing import Optional
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
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

    if transfile2.filename != '':
        transaction_files.append(
            {'name': transfile2.filename, 'format': transformat2, 'fd': transfile2.file})
    if wirefile.filename == '':
        wirefile = None
    if holdfile.filename == '':
        holdfile = None
    try:
        report, holdings = do_taxes(
            broker, transaction_files, holdfile, wirefile, year)
    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    return ESPPResponse(tax_report=report, holdings=holdings)


@app.get("/")
async def main():
    '''Main page'''
    content = """
<body>
<form action="/files/" enctype="multipart/form-data" method="post">
<label for="transfile1">Transactions:</label>
<input type="file" id="transfile1" name="transfile1">
<label for="transformat1">Format:</label>
<select id="transformat1" name="transformat1">
  <option value="schwab" selected>schwab</option>
  <option value="td">td</option>
  <option value="pickle">pickle</option>
  <option value="morgan">morgan</option>
</select>
<br>
<label for="transfile2">Transactions #2:</label>
<input type="file" id="transfile2" name="transfile2">
<label for="transformat2">Format:</label>
<select id="transformat2" name="transformat2">
  <option value="schwab" selected>schwab</option>
  <option value="td">td</option>
  <option value="pickle">pickle</option>
  <option value="morgan">morgan</option>
</select>
<br>
<label for="holdfile">Previous year holdings:</label>
<input type="file" id="holdfile" name="holdfile">
<br>
<label for="wirefile">Wires:</label>
<input type="file" id="wirefile" name="wirefile">
<br>

<label for="year">Year:</label>
<select id="year" name="year">
  <option value="2021">2021</option>
  <option value="2022" selected>2022</option>
</select>
<select id="broker" name="broker">
  <option value="schwab" selected>schwab</option>
  <option value="td">td</option>
  <option value="morgan">morgan</option>
</select>

<input type="submit">
</form>
</body>
    """
    return HTMLResponse(content=content)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
