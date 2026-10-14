FROM python:3.11-slim
WORKDIR /app
COPY frontend/requirements.txt frontend/requirements.txt
RUN pip install --no-cache-dir -r frontend/requirements.txt
COPY backend/app backend/app
COPY frontend/streamlit_app.py frontend/streamlit_app.py
COPY .streamlit .streamlit
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "frontend/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
