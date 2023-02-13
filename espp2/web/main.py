#!/usr/bin/env python3

'''
ESPP2 web server
'''

from typing import Optional
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
from espp2.main import do_taxes, Log

app = FastAPI()

import json, typing
from starlette.responses import Response

class PrettyJSONResponse(Response):
    media_type = "application/json"

    def render(self, content: typing.Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=4,
            separators=(", ", ": "),
        ).encode("utf-8")

@app.post("/files/", response_class=PrettyJSONResponse)
async def create_files(
        transfile: UploadFile,
        transformat: str = Form(...),
        holdfile: Optional[UploadFile] = None,
        wirefile: UploadFile = File(None),
        year: int = Form(...)):
    '''File upload endpoint'''
    log = Log()
    try:
        report, holdings = do_taxes(
            transfile, transformat, holdfile, wirefile, year, log)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"report": report, "holdings": holdings}


@app.get("/")
async def main():
    '''Main page'''
    content = """
<body>
<form action="/files/" enctype="multipart/form-data" method="post">
<label for="transfile">Transactions:</label>
<input type="file" id="transfile" name="transfile">
<label for="transformat">Format:</label>
<select id="transformat" name="transformat">
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
<input type="submit">
</form>
</body>
    """
    return HTMLResponse(content=content)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
