from fastapi import FastAPI
from models import TickerImgReq
import bot
from fastapi.middleware.cors import CORSMiddleware

__version__ = "0.1.0"

def lifespan():
    # Any startup code can be placed here
    print("Starting up the API...")
    yield
    # Any shutdown code can be placed here
    print("Shutting down the API...")
    
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.get("/")
def root():
    return  {
        "Services": get_health(),
        "Version": __version__
    }
    

app.get("/ticker-image-path")
def get_ticker_img_path(TickerImgReq: TickerImgReq):
    return bot.getChartImagePath(TickerImgReq.ticker)
    
    
def get_health() -> str:
    health = True
    if health: return "Healthy"
    else: return "Services disfunctional"


if __file__ == "__main__":
    import uvicorn
    bot.init()
    
    uvicorn.run(app, host="127.0.0.1", port=8000)

    
