import os
import json
import sqlite3
import requests
from datetime import datetime

# ===== তোমার প্রোফাইল (নিজের মতো বদলাও) =====
MY_PROFILE = """
আমার স্কিল: MS Office, Excel, Data Entry, English, Computer Operation
লোকেশন: Dhaka
অভিজ্ঞতা: Fresher
পছন্দের জব: Data Entry, Office Assistant, Computer Operator, Admin, Govt job, IT related
"""

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

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

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("Telegram credentials missing")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={
                "chat_id": TG_CHAT_ID,
                "text": text,
                "disable_web_page_preview": True
            },
            timeout=20
        )
        print("Telegram:", r.status_code)
        return r.status_code == 200
    except Exception as e:
        print("Telegram error:", e)
        return False

def get_bdjobs(pages=2):
    """BDJobs API থেকে জব আনে (সঠিক পার্সিং)"""
    jobs = []
    # নতুন কাজ করা API
    base_url = "https://api.bdjobs.com/Jobs/api/JobSearch/GetJobSearch"
    
    for pg in range(1, pages + 1):
        url = f"{base_url}?isPro=1&rpp=40&pg={pg}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            print(f"BDJobs page {pg} status:", r.status_code)
            
            if r.status_code != 200:
                print("Response text:", r.text[:300])
                continue
                
            data = r.json()
            
            # data এবং premiumData দুটোই লিস্ট
            job_list = []
            if isinstance(data, dict):
                if isinstance(data.get("data"), list):
                    job_list.extend(data["data"])
                if isinstance(data.get("premiumData"), list):
                    job_list.extend(data["premiumData"])
            
            print(f"Page {pg} jobs found:", len(job_list))
            
            for j in job_list:
                if not isinstance(j, dict):
                    continue
                    
                # ফিল্ড নামগুলো API অনুযায়ী
                title = (j.get("jobTitle") or j.get("JobTitle") or j.get("title") or "").strip()
                company = (j.get("companyName") or j.get("CompanyName") or j.get("CompnayName") or "").strip()
                link_id = j.get("Jobid") or j.get("JobId") or j.get("jobId") or j.get("id") or ""
                location = (j.get("location") or j.get("JobLocation") or "Bangladesh").strip()
                deadline = j.get("deadline") or j.get("Deadline") or ""
                
                if title and link_id:
                    # জব লিংক
                    link = f"https://bdjobs.com/h/details/{link_id}"
                    
                    jobs.append({
                        "id": str(link_id),
                        "title": title,
                        "company": company,
                        "location": location,
                        "deadline": deadline,
                        "link": link,
                        "source": "BDJobs"
                    })
                    
        except Exception as e:
            print(f"BDJobs page {pg} error:", e)
            
    # ডুপ্লিকেট সরানো
    unique = {}
    for j in jobs:
        unique[j["id"]] = j
    return list(unique.values())

def ai_filter(jobs):
    if not jobs:
        return []
        
    if not GEMINI_API_KEY:
        print("No Gemini key → first 8 jobs পাঠাচ্ছি")
        return jobs[:8]

    job_text = "\n".join(
        [f"{i}. {j['title']} - {j['company']} ({j['location']})" for i, j in enumerate(jobs)]
    )
    
    prompt = f"""আমার প্রোফাইল:
{MY_PROFILE}

নিচের জব লিস্ট থেকে আমার সাথে মোটামুটি মিল আছে এমন জবগুলোর ইনডেক্স নম্বর বাছাই করো।
খুব কঠোর হয়ো না — একটু মিললেই নাও (Fresher/Office/Data/Admin/Computer হলে প্রায়ই মিলবে)।
শুধু JSON অ্যারে রিটার্ন করো, যেমন: [0, 2, 5, 7]
অন্য কোনো কথা লিখবে না।

জব লিস্ট:
{job_text}
"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300}
        }
        r = requests.post(url, json=payload, timeout=45)
        print("Gemini status:", r.status_code)
        
        result = r.json()
        
        if "candidates" not in result:
            print("Gemini error response:", str(result)[:400])
            return jobs[:6]
            
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        print("AI reply:", text[:200])
        
        start = text.find("[")
        end = text.rfind("]") + 1
        if start != -1 and end > start:
            idx = json.loads(text[start:end])
            matched = [jobs[i] for i in idx if isinstance(i, int) and 0 <= i < len(jobs)]
            if matched:
                return matched
    except Exception as e:
        print("AI error:", e)
    
    return jobs[:6]  # ফেইল হলে কিছু জব পাঠাবে

if __name__ == "__main__":
    print("=" * 50)
    print("Job Agent started:", datetime.now())
    
    # শুরু মেসেজ
    send_telegram(f"🤖 Job Agent চালু হয়েছে\nসময়: {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    
    all_jobs = get_bdjobs(pages=2)
    print(f"Total fetched: {len(all_jobs)}")

    new_jobs = [j for j in all_jobs if is_new(j["id"])]
    print(f"New jobs: {len(new_jobs)}")

    if new_jobs:
        matched = ai_filter(new_jobs)
        print(f"Matched: {len(matched)}")
        
        if matched:
            send_telegram(f"✅ {len(matched)}টা ম্যাচিং জব পাওয়া গেছে:")
            for job in matched:
                msg = f"""🆕 {job['title']}
🏢 {job['company']}
📍 {job['location']}
📅 Deadline: {job.get('deadline') or 'N/A'}
🔗 {job['link']}"""
                send_telegram(msg)
        else:
            send_telegram("ℹ️ নতুন জব আছে, কিন্তু প্রোফাইলের সাথে ভালো ম্যাচ হয়নি।")
    else:
        send_telegram("ℹ️ এবার কোনো নতুন জব পাওয়া যায়নি (আগেরগুলোই দেখা).")
    
    print("Done.")
    print("=" * 50)
