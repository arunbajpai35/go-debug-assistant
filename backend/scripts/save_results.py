import psycopg2
import configparser
from datetime import datetime

config = configparser.ConfigParser()
config.read("config/config.ini")

db_config = config["database"]

def save_to_postgres(trace_id, service, log, ai_summary, root_cause, suggestion):
    try:
        conn = psycopg2.connect(
            host=db_config["host"],
            port=db_config.getint("port"),
            user=db_config["user"],
            password=db_config["password"],
            database=db_config["dbname"]
        )
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO analysis_results (
                trace_id, service, log, ai_summary, root_cause, suggestion, timestamp
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            trace_id, service, log, ai_summary, root_cause, suggestion, datetime.utcnow()
        ))

        conn.commit()
        cur.close()
        conn.close()

        print(f"[DB Save Success] Saved analysis for trace_id={trace_id}")
    except Exception as e:
        print(f"[DB Save Error] {e}")
