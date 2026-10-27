import os
import json
import sqlite3
import hashlib
import requests
from datetime import datetime

# ===== তোমার প্রোফাইল এখানে লিখো =====
MY_PROFILE = """
আমার স্কিল: Python, MS Office, Data Entry, English
লোকেশন: Dhaka
অভিজ্ঞতা: 0-2 years
পছন্দের জব: IT, Software, Office Assistant, Data related, Govt job
"""

# API Keys (GitHub Secrets থেকে আসবে)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Database (ডুপ্লিকেট জব আটকাতে)
db = sqlite3.connect("jobs.db")
db.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY)")
db.commit()

def is_new(job_id):
    jid = str(job_id)
    if db.execute("SELECT 1 FROM seen WHERE id=?", (jid,)).fetchone():
        return False
    db.execute("INSERT INTO seen VALUES (?)", (jid,))
    db.commit()
    return True

def get_bdjobs(keyword=" ", pages=2):
    """BDJobs থেকে লেটেস্ট জব আনে (তাদের পাবলিক API ব্যবহার করে)"""
    jobs = []
    for pg in range(1, pages + 1):
        url = f"https://gateway.bdjobs.com/recruitment-account-test/api/JobSearch/GetJobSearch?isPro=1&rpp=30&pg={pg}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            data = r.json()
            # API রেসপন্স স্ট্রাকচার চেক
            job_list = data.get("data", {}).get("joblist", []) or data.get("joblist", []) or []
            if not job_list and isinstance(data.get("data"), list):
                job_list = data.get("data")
            for j in job_list:
                title = j.get("JobTitle") or j.get("jobTitle") or j.get("title") or ""
                company = j.get("CompnayName") or j.get("CompanyName") or j.get("company") or ""
                link_id = j.get("JobId") or j.get("jobId") or j.get("id") or ""
                location = j.get("JobLocation") or j.get("location") or "Bangladesh"
                if title and link_id:
                    link = f"https://jobs.bdjobs.com/jobdetails.asp?id={link_id}" if str(link_id).isdigit() else f"https://www.bdjobs.com/{link_id}"
                    jobs.append({
                        "id": str(link_id),
                        "title": title.strip(),
                        "company": company.strip(),
                        "location": location,
                        "link": link,
                        "source": "BDJobs"
                    })
        except Exception as e:
            print(f"BDJobs page {pg} error:", e)
    return jobs

def ai_filter(jobs):
    if not jobs or not GEMINI_API_KEY:
        return jobs[:5]  # AI না থাকলে প্রথম কয়েকটা পাঠাবে

    # সহজ প্রম্পট
    job_text = "\n".join([f"{i}. {j['title']} - {j['company']} ({j['location']})" for i, j in enumerate(jobs)])
    prompt = f"""
তোমার কাজ: নিচের জব লিস্ট থেকে শুধু আমার প্রোফাইলের সাথে মিলে যায় এমন জবগুলোর ইনডেক্স নম্বর বাছাই করো।
আমার প্রোফাইল:
{MY_PROFILE}

জব লিস্ট:
{job_text}

শুধু JSON অ্যারে রিটার্ন করো, যেমন: [0, 2, 5]
অন্য কিছু লিখবে না।
"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2}
        }
        r = requests.post(url, json=payload, timeout=30)
        result = r.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        # JSON অংশ বের করা
        start = text.find("[")
        end = text.rfind("]") + 1
        if start != -1:
            idx = json.loads(text[start:end])
            return [jobs[i] for i in idx if isinstance(i, int) and i < len(jobs)]
    except Exception as e:
        print("AI error:", e)
    return jobs[:3]  # ফেইল হলে কিছু পাঠাবে

def send_telegram(job):
    msg = f"""🆕 নতুন জব মিলেছে!

📌 {job['title']}
🏢 {job['company']}
📍 {job['location']}
🔗 {job['link']}
📅 {datetime.now().strftime('%d %b %Y')}
"""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": msg},
            timeout=15
        )
        print("Sent:", job['title'])
    except Exception as e:
        print("Telegram error:", e)

if __name__ == "__main__":
    print("Job Agent started...")
    all_jobs = get_bdjobs(pages=2)  # ২ পেজ ≈ ৬০ জব
    print(f"Total fetched: {len(all_jobs)}")

    new_jobs = [j for j in all_jobs if is_new(j["id"])]
    print(f"New jobs: {len(new_jobs)}")

    if new_jobs:
        matched = ai_filter(new_jobs)
        print(f"Matched: {len(matched)}")
        for job in matched:
            send_telegram(job)
    else:
        print("No new jobs today.")
    print("Done.")
