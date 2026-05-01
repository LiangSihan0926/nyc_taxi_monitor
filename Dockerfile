# 1. Base Image: Use a lightweight, modern version of Python
FROM python:3.10-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Install required system tools (like 'make' for your Makefile)
RUN apt-get update && apt-get install -y make && rm -rf /var/lib/apt/lists/*

# 4. Copy everything from your local folder into the container
# (This includes your code, pyproject.toml, and your reports/ folder)
COPY . /app/

# 5. Install the project dependencies (including Streamlit from your 'viz' group)
RUN pip install --no-cache-dir -e ".[dev,viz]"

# 6. Open the port that Streamlit uses to broadcast the web page
EXPOSE 8501

# 7. The default command: Run the dashboard when the container starts
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
