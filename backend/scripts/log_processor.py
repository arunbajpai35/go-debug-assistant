# log_processor.py
from kafka import KafkaConsumer
import json, uuid, time
import redis
import psycopg2  # or use asyncpg or SQLAlchemy later
from ai_analyzer import analyze_log  # you’ll implement this or use the /analyze API

# Redis setup
r = redis.Redis(host='localhost', port=6379, db=0)

# PostgreSQL setup
pg_conn = psycopg2.connect(
    dbname="debug_logs", user="postgres", password="yourpass", host="localhost"
)
pg_cursor = pg_conn.cursor()

# Kafka Consumer
consumer = KafkaConsumer(
    'log-ingestion',
    bootstrap_servers='localhost:9092',
    auto_offset_reset='earliest',
    value_deserializer=lambda v: json.loads(v.decode('utf-8'))
)

print("Listening and analyzing...\n")

for message in consumer:
    log = message.value
    log_id = str(uuid.uuid4())
    log['id'] = log_id
    log['timestamp'] = time.time()

    # 1. AI Analysis
    analysis = analyze_log(log)
    log['analysis'] = analysis

    # 2. Cache in Redis
    r.set(f"log:{log_id}", json.dumps(log))
    r.lpush("recent_logs", log_id)
    r.ltrim("recent_logs", 0, 99)  # Keep only 100 recent logs

    # 3. Store in PostgreSQL
    pg_cursor.execute(
        """
        INSERT INTO logs (id, service, level, msg, timestamp, analysis)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (log_id, log['service'], log['level'], log['msg'], log['timestamp'], analysis)
    )
    pg_conn.commit()

    print(f"[✔] Processed log: {log_id}")
