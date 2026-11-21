from pydantic import BaseModel

    
class TickerImgReq(BaseModel):
    ticker: str
    img_type: str
    
class TickerDataRes(BaseModel):
    ticker: str
    img_path: str
