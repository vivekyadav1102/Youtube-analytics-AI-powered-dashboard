import os
from datetime import datetime
from dotenv import load_dotenv
import pickle
import time
import streamlit as st
import pandas as pd
import plotly.express as px
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.generativeai as genai

# ==============================
#  STREAMLIT PAGE CONFIG
# ==============================
st.set_page_config(page_title="YouTube Analytics Dashboard", layout="wide")

# ==============================
#  CUSTOM CSS
# ==============================
st.markdown("""
    <style>
    body {
        background-color: #0e1117;
        color: white;
    }
    .stApp {
        background-color: #0e1117;
    }
    .stButton>button {
        background-color: #FF0000;
        color: white;
        border-radius: 10px;
        padding: 8px 16px;
    }
    .stButton>button:hover {
        background-color: #cc0000;
        color: white;
    }
    .css-1d391kg, .css-1v3fvcr {
        background-color: #161a23 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==============================
#  GOOGLE & GEMINI SETUP
# ==============================
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
TOKEN_PICKLE = "token.pkl"

# Load variables from .env file
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ No GEMINI_API_KEY found. Please set it in your .env file.")

# Configure Gemini model
genai.configure(api_key=api_key)
gemini_model = genai.GenerativeModel("gemini-2.5-flash")

# ==============================
#  AUTHENTICATION HANDLER
# ==============================
def get_authenticated_service():
    """Authenticate YouTube API and return service object"""
    creds = None
    if os.path.exists(TOKEN_PICKLE):
        with open(TOKEN_PICKLE, "rb") as token:
            creds = pickle.load(token)
    if not creds:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_PICKLE, "wb") as token:
            pickle.dump(creds, token)
    return build("youtube", "v3", credentials=creds)

# ==============================
#  GET CHANNEL STATS
# ==============================
def get_channel_stats(youtube):
    request = youtube.channels().list(
        part="snippet,statistics,contentDetails",
        mine=True
    )
    response = request.execute()
    return response["items"][0]

# ==============================
#  GET LATEST 10 VIDEOS
# ==============================
def get_latest_videos(youtube, max_results=10):
    request = youtube.search().list(
        part="snippet",
        forMine=True,
        type="video",
        order="date",
        maxResults=max_results
    )
    response = request.execute()
    videos = []
    for idx, item in enumerate(response["items"], start=1):  # Start index from 1
        videos.append({
            "S.No": idx,
            "title": item["snippet"]["title"],
            "publishedAt": item["snippet"]["publishedAt"]
        })
    return videos

# ==============================
#  GET VIDEO STATS (TOP VIDEOS)
# ==============================
def get_video_stats(youtube, video_ids):
    request = youtube.videos().list(
        part="snippet,statistics",
        id=",".join(video_ids)
    )
    response = request.execute()
    videos = []
    for item in response["items"]:
        stats = item["statistics"]
        videos.append({
            "title": item["snippet"]["title"],
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0))
        })
    return videos

# ==============================
#  SAVE DAILY STATS
# ==============================
def save_daily_stats(subs, views, videos, file="channel_history.csv"):
    """
    Save daily channel statistics (subscribers, views, videos) to a CSV file.
    Ensures only one record per date is stored.
    """
    if os.path.exists(file):
        df = pd.read_csv(file)
    else:
        df = pd.DataFrame(columns=["date", "subscribers", "views", "videos"])

    today = datetime.today().strftime("%Y-%m-%d")

    if today not in df["date"].values:
        new_row = {"date": today, "subscribers": subs, "views": views, "videos": videos}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(file, index=False)
    
# ==============================
#  AI INSIGHTS USING GEMINI
# ==============================
def generate_ai_insights(videos):
    df = pd.DataFrame(videos)
    prompt = f"""
    Analyze the following YouTube video performance data and provide:
    1. Key insights about which content works best.
    2. Suggested improvements for titles/thumbnails/engagement.
    3. A future content strategy for growth.

    Data:
    {df.to_string(index=False)}
    """
    response = gemini_model.generate_content(prompt)
    return response.text

# ==============================
#  MAIN APP
# ==============================
st.title("YouTube Analytics Dashboard")
st.write("Track your channel performance and get AI-powered content strategy insights.")

# Button to switch accounts (delete token and re-authenticate)
if st.button("🔄 Change YouTube Account", key="change_acc"):
    if os.path.exists(TOKEN_PICKLE):
        os.remove(TOKEN_PICKLE)
    st.success("Token cleared. Please refresh and sign in with another account.")
    st.stop()

try:
    youtube = get_authenticated_service()

    # Fetch channel data
    channel_data = get_channel_stats(youtube)
    channel_name = channel_data["snippet"]["title"]
    subs = int(channel_data["statistics"]["subscriberCount"])
    views = int(channel_data["statistics"]["viewCount"])
    videos_count = int(channel_data["statistics"]["videoCount"])

    # Save stats daily
    save_daily_stats(subs, views, videos_count)

    # ==============================
    #  CHANNEL STATS CARDS
    # ==============================
    st.subheader(f"Channel: {channel_name}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Subscribers", subs)
    c2.metric("Total Views", views)
    c3.metric("Videos", videos_count)

    

    # ==============================
    #  TRENDLINE CHART
    # ==============================
    st.subheader("📈 Channel Growth Over Time")
    if os.path.exists("channel_history.csv"):
        history_df = pd.read_csv("channel_history.csv")
        fig_trend = px.line(
            history_df,
            x="date",
            y=["subscribers", "views", "videos"],
            markers=True,
            title="Channel Growth Trends"
        )
        st.plotly_chart(fig_trend, use_container_width=True)
        # Download option for historical data
        csv = history_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download Channel History (CSV)",
            data=csv,
            file_name="channel_history.csv",
            mime="text/csv"
        )


    # ==============================
    #  TOP 10 VIDEOS (by Views)
    # ==============================
    st.subheader("🔥 Top 10 Videos (by Views)")
    uploads_playlist = channel_data["contentDetails"]["relatedPlaylists"]["uploads"]

    playlist_items = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=uploads_playlist,
        maxResults=20
    ).execute()

    video_ids = [item["contentDetails"]["videoId"] for item in playlist_items["items"]]
    video_stats = get_video_stats(youtube, video_ids)

    df_videos = pd.DataFrame(video_stats).sort_values(by="views", ascending=False).head(10)
    st.table(df_videos[["title", "views", "likes", "comments"]])

    fig = px.bar(df_videos, x="title", y="views", title="Top 10 Videos by Views", text="views")
    st.plotly_chart(fig, use_container_width=True)

    # ==============================
    #  LATEST 10 VIDEOS
    # ==============================
    st.subheader("🆕 Latest 10 Videos")
    latest_videos = get_latest_videos(youtube, 10)
    df_latest = pd.DataFrame(latest_videos)
    st.table(df_latest)

    # ==============================
    #  AI INSIGHTS SECTION
    # ==============================
    st.subheader("🤖 AI Insights & Content Strategy")
    if st.button("Generate AI Insights"):
        with st.spinner("Generating insights... Please wait ⏳"):
            insights = generate_ai_insights(video_stats)
        st.success("✅ Insights generated successfully!")
        st.write(insights)


    # ==============================
    #  AUTO REFRESH OPTION
    # ==============================
    refresh = st.checkbox("Auto-refresh every 60 seconds")
    if refresh:
        time.sleep(60)
        st.experimental_rerun()

except HttpError as e:
    st.error(f"API Error: {e}")
