FROM python:3.11-slim

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    git build-essential linux-headers-amd64 tzdata ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Set timezone (use Asia/Kolkata if needed)
ENV TZ=Asia/Dhaka

RUN pip install --no-cache-dir -U pip wheel==0.45.1

WORKDIR /app

# প্রথমে requirements.txt কপি করুন এবং ইন্সটল করুন
# নিশ্চিত করুন যে requirements.txt ফাইলে fastapi এবং uvicorn আছে
COPY requirements.txt /app
RUN pip install -U -r requirements.txt

# প্রজেক্টের বাকি ফাইলগুলো কপি করুন (main.py, app.py, helpers, ইত্যাদি)
COPY . /app

# পরিবর্তন: python3 main.py কে ব্যাকগ্রাউন্ডে (&) চালান
# এবং uvicorn কে ফোরগ্রাউন্ডে চালান
# এটি start.sh ফাইলের প্রয়োজনীয়তা দূর করে
CMD python3 main.py & uvicorn app:app --host 0.0.0.0 --port $PORT
